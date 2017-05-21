from getData import getChapters, getPages, getImage 

from signal import signal, SIGINT
from time import time, sleep
from sys import argv, exit
from stat import S_IFDIR, S_IFLNK, S_IFREG
from fuse import FUSE, FuseOSError, Operations, fuse_get_context
from subprocess import Popen, PIPE
import re
import os
from errno import ENOENT
from threading import Thread, Condition
from queue import Queue

class MangaReaderFS(Operations):
    def __init__(self, rfile, cv, tasks):
        self.rfile = rfile
        reading_list = open(rfile, 'r')
        names = reading_list.readlines()
        names = list(map(lambda x: x.replace("\n", ""), names))
        self.reading_list = names
        self.cache = dict()
        self.filecache = dict()
        self.fd = 0
        self.cv = cv
        self.tasks = tasks

    def readdir(self, path, fh):
        if path == '/':
            reading_list = open(self.rfile, 'r')
            names = reading_list.readlines()
            names = list(map(lambda x: x.replace("\n", ""), names))
            self.reading_list = names
            return ['.', '..'] + self.reading_list
        elif path[1:] in self.reading_list:
            _, _, pid = fuse_get_context()
            p = Popen(['ps', '-p', str(pid), '-o', 'comm='], stdout=PIPE)
            r = p.communicate()
            r = r[0].decode()
            if r == 'rm\n':
                return ['.','..']

            if path[1:] in self.cache:
                return ['.', '..'] + self.cache[path[1:]]
            else:
                chapters = list(map(lambda x: x.split('/')[-1],
                                      getChapters(path[1:])))
                #print("chapters: ", chapters)
                for i in range(len(chapters)):
                    while len(chapters[i])<3:
                        chapters[i] = '0'+chapters[i]
                
                self.cache[path[1:]] = chapters
                return ['.', '..'] + chapters
        else:
            parts = path.split('/')
            chapter = parts[-1]
            name = parts[-2]
            if re.match("[0-9]+", chapter) and name in self.reading_list:

                pages = list(map(lambda x: str(x+1), range(getPages(name,
                    chapter))))
                for i in range(len(pages)):
                    while len(pages[i])<3:
                        pages[i] = '0' + pages[i]

                return ['.', '..'] + pages
            else:
                raise FuseOSError(ENOENT)

    def loadCache(self, name, chapter):
        self.cv.acquire()
        if not name in self.filecache:
            self.filecache[name] = dict()
        if not chapter in self.filecache[name]:
            self.filecache[name][chapter] = dict()
            self.filecache[name][chapter]['timestamp'] = time()
        self.cv.release()

        pages = list(map(lambda x: str(x+1), range(getPages(name,
            chapter))))
        for i in range(len(pages)):
            while len(pages[i])<3:
                pages[i] = '0' + pages[i]
            self.tasks.put('/'.join([name, chapter, pages[i]]))

    def mkdir(self, path, mode):
        if '/' not in path[1:]:
          #only allows files in root dir
          self.reading_list.append(path[1:])
          with open(self.rfile, 'w') as f:
              f.write("\n".join(self.reading_list))
          return 0

    def unlink(self, path):
        print("Unlinking", path)
        print(fuse_get_context())
        return 0

    def rmdir(self, path):
        if '/' not in path[1:]:
            print("deleting ", path)
            self.reading_list.remove(path[1:])
            with open(self.rfile, 'w') as f:
                f.write("\n".join(self.reading_list))
        return 0

    def rename(self, old, new):
        print('--------')
        print(self.reading_list)
        self.cv.acquire()
        print(old, new)
        old = old[1:]
        new = new[1:]
        r = self.filecache.pop(old, None)
        try:
            self.reading_list.remove(old)
        except:
            pass
        self.reading_list.append(new)
        print(self.reading_list)
        with open(self.rfile, 'w') as f:
            f.write("\n".join(self.reading_list))
        self.cv.release()
        print('--------')
        return 0

    def open(self, path, flags):
        parts = path.split('/')
        print("opening "+path)
        self.fd += 1
        return self.fd

    def read(self, path, size, offset, fh):
        parts = path.split('/')
        page = parts[-1]
        chapter = parts[-2]
        name = parts[-3] 

        if re.match("[0-9]+", page) and re.match("[0-9]+", chapter)\
            and name in self.reading_list:
                self.cv.acquire()
                if not name in self.filecache or\
                   not chapter in self.filecache[name]:
                       self.loadCache(name, chapter)

                flag = 0
                while name not in self.filecache or \
                      chapter not in self.filecache[name] or\
                      page not in self.filecache[name][chapter]:
                    
                    if name not in self.filecache or\
                       chapter not in self.filecache[name]:
                              #todo figure out if this is still necessary
                              flag = 1
                              break
                    self.cv.wait()
                
                f = None
                if flag:
                    f = getImage(name, chapter, page)
                else:
                    f = self.filecache[name][chapter][page]
                    self.filecache[name][chapter]['timestamp'] = time()
                self.cv.release()

                return f[offset:offset+size]

        print("reading "+path+" "+str(size)+" "+str(offset))
        ret = os.read(os.open('temp.txt', os.O_RDONLY), size)
        print(ret)
        return ret
    def getattr(self, path, fh):
        parts = path.split('/')

        if path[1:] in self.reading_list:
            return dict(st_mode=(S_IFDIR), st_nlink=2,
                        st_ctime=time(),
                        st_mtime=time(),
                        st_atime=time())

        if re.match("[0-9]+", parts[-1]) and parts[-2] in self.reading_list:
            return dict(st_mode=(S_IFDIR), st_nlink=2,
                        st_ctime=time(),
                        st_mtime=time(),
                        st_atime=time())

        if re.match("[0-9]+", parts[-1]) and re.match("[0-9]+", parts[-2])\
            and parts[-3] in self.reading_list:
                name = parts[-3]
                chapter = parts[-2]

                return dict(st_mode=(S_IFREG), st_nlink=1,
                       st_size=1000000000,
                       st_ctime=time(),
                       st_mtime=time(),
                       st_atime=time())
        
        st = os.lstat(path)
        return dict((key, getattr(st, key)) for key in ('st_atime',
                                                        'st_ctime',
                                                        'st_gid',
                                                        'st_mode',
                                                        'st_mtime',
                                                        'st_nlink',
                                                        'st_size',
                                                        'st_uid'))

def worker(tasks, cv, fs):
    while 1:
        path = tasks.get()
        
        if path==None:
            print("Exiting")
            tasks.task_done()
            break

        parts = path.split('/')
        page = parts[-1]
        chapter = parts[-2]
        name = parts[-3]

        cv.acquire()

        if name in fs.filecache and\
           chapter in fs.filecache[name] and\
           page in fs.filecache[name][chapter]:
            cv.notifyAll()
            cv.release()
            tasks.task_done()
            continue
        cv.release()
        print("downloading:", path)
        img = getImage(name, chapter, page)

        cv.acquire()
        if not name in fs.filecache or\
           not chapter in fs.filecache[name]:
           print("Not in cache!", path, fs.filecache_name, fs.filecache_chapter)
           print(name, chapter)
           cv.release()
           tasks.task_done()
           continue
        fs.filecache[name][chapter][page] = img
        tasks.task_done()
        print("Got the file!", path)
        cv.notifyAll()
        cv.release()

def cleanCache(fs, cv):
    while 1:
        sleep(300)
        cv.acquire()
        for n in fs.filecache:
            for c in fs.filecache[n]:
                if time() - fs.filecache[n][c]['timestamp'] > 300:
                    print("Deleting chapter", c, "of", n)
                    del fs.filecache[n][c]
            if len(fs.filecache[n].keys()) == 0:
                print("Deleting", n)
                del fs.filecache[n]
        cv.notifyAll()
        cv.release()





workerThreads = []
tasks = Queue()
numThreads = 20

def main(mountpoint, rfile):
    cv = Condition()

    fs = MangaReaderFS(rfile, cv, tasks)
    
    for i in range(numThreads):
        t = Thread(target = worker, args=(tasks, cv, fs))
        workerThreads.append(t)
        t.start()

    cleaner = Thread(target = cleanCache, args=(fs,cv))
    cleaner.start()

    FUSE(fs, mountpoint, foreground=True)

def sig_handler(signal, frame):
    for i in range(numThreads):
        tasks.put(None)
    tasks.join()
    for t in workerThreads:
      t.join()
    exit(0)   

if __name__ == '__main__':
    signal(SIGINT, sig_handler)
    if(len(argv)<2):
        print("Usage: \n\tpython3 mangareaderFS.py [mountpoint] [readinglist] (numThreads)\n\t\
         where numThreads is optional and defaults to 20\n\t\
         and readinglist is a file containing the manga you want to read (this can be updated by creating/deleting files)")
    if(len(argv)>3):
        numThreads = int(argv[3])
    main(argv[1], argv[2])
