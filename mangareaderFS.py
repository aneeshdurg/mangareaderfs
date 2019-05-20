import re
import os

from errno import ENOENT
from fuse import FUSE, FuseOSError, Operations, fuse_get_context
from queue import Queue
from signal import signal, SIGINT
from stat import S_IFDIR, S_IFLNK, S_IFREG
from subprocess import Popen, PIPE
from sys import argv, exit
from threading import Thread, Condition
from time import time, sleep

from getData import getChapters, getPages, getImage

class MangaReaderFS(Operations):
    def __init__(self, rfile, cv, tasks, mnt):
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
        self.mnt = mnt

    @staticmethod
    def _pad_items_to_max(items):
        # A hacky way to approximate log base 10 without floats
        # We add 1 to enforce a leading 0 to get proper sorting when
        # listing the directory
        max_strlen = len(str(len(items))) + 1

        # Pad each page with leading 0s to have uniform length +
        # sorting order
        return list(map(lambda x: x.zfill(max_strlen), items))


    def readdir(self, path, fh):
        defaults = ['.', '..']
        if path == '/':
            reading_list = open(self.rfile, 'r')
            names = reading_list.readlines()
            names = list(
                filter(lambda x: len(x),
                    map(lambda x: x.strip(), names)))
            self.reading_list = names
            return defaults + self.reading_list

        if '/' not in path[1:]:
            name = path[1:]

            try:
                return defaults + self.cache[name]['chapters']
            except KeyError:
                if name not in self.cache:
                  self.cache[name] = dict()
                chapters = list(map(lambda x: x.split('/')[-1],
                                      getChapters(name)))
                chapters = MangaReaderFS._pad_items_to_max(chapters)
                self.cache[name]['chapters'] = chapters
                return defaults + self.cache[name]['chapters']

        else:
            parts = path.split('/')
            name = parts[-2]
            chapter = parts[-1]
            if not all(
                    [re.match("[0-9]+", chapter), name in self.reading_list]):
                raise FuseOSError(ENOENT)

            def get_pages_from_cache(name, chapter):
                page_count = self.cache[name]['pages'][int(chapter)]
                pages = list(map(str, range(1, 1 + page_count)))
                pages = MangaReaderFS._pad_items_to_max(pages)
                return pages

            try:
                return defaults + get_pages_from_cache(name, chapter)
            except KeyError:
                page_count = getPages(name, chapter)
                if name not in self.cache:
                    self.cache[name] = dict()

                if 'pages' not in self.cache[name]:
                    self.cache[name]['pages'] = dict()

                self.cache[name]['pages'][int(chapter)] = page_count
                return defaults + get_pages_from_cache(name, chapter)


    def loadCache(self, name, chapter):
        self.cv.acquire()
        if not name in self.filecache:
            self.filecache[name] = dict()
        if not chapter in self.filecache[name]:
            self.filecache[name][chapter] = dict()
            self.filecache[name][chapter]['timestamp'] = time()
        self.cv.release()

        pages = list(map(str, range(1, 1 + getPages(name, chapter))))
        pages = MangaReaderFS._pad_items_to_max(pages)

        for page in pages:
            self.tasks.put('/'.join([name, chapter, page]))

    def mkdir(self, path, mode):
        if '/' not in path[1:]:
          #only allows files in root dir
          self.reading_list.append(path[1:])
          with open(self.rfile, 'w') as f:
              f.write("\n".join(self.reading_list))
          return 0

    def rmdir(self, path):
        if '/' not in path[1:]:
            print("deleting ", path)
            self.reading_list.remove(path[1:])
            with open(self.rfile, 'w') as f:
                f.write("\n".join(self.reading_list))
            try:
                del self.cache[name]
            except:
                pass
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
        page = parts[-1]
        chapter = parts[-2]
        name = parts[-3]

        self.cv.acquire()
        if not name in self.filecache or\
           not chapter in self.filecache[name]:
               self.loadCache(name, chapter)
        self.cv.release()

        print("opening "+path)

        self.fd += 1
        return self.fd

    def create(self, path, fh):
        return 0

    def read(self, path, size, offset, fh):
        parts = path.split('/')
        page = parts[-1]
        chapter = parts[-2]
        name = parts[-3]

        if re.match("[0-9]+", page) and re.match("[0-9]+", chapter)\
            and name in self.reading_list:
                self.cv.acquire()

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
                    f = self.filecache[name][chapter][page][0]
                    self.filecache[name][chapter]['timestamp'] = time()
                self.cv.release()

                return f[offset:offset+size]

        raise FuseOSError(ENOENT)

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
                page = parts[-1]
                size = 4096
                t = 0

                self.cv.acquire()
                if name in self.filecache and\
                   chapter in self.filecache[name] and\
                   page in self.filecache[name][chapter]:
                   size = len(self.filecache[name][chapter][page][0])
                   t = self.filecache[name][chapter][page][1]
                   #print("size of", path, "is", size, type(self.filecache[name][chapter][page]))
                self.cv.release()

                return dict(st_mode=(S_IFREG), st_nlink=1,
                       st_size=size,
                       st_ctime=t,
                       st_mtime=t,
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

        fs.filecache[name][chapter][page] = (img, time())
        tasks.task_done()
        print("Got the file!", path)
        cv.notifyAll()
        cv.release()

def cleanCache(fs, cv):
    timeout = 300
    while True:
        sleep(timeout)
        cv.acquire()
        oldNames = []
        for n in fs.filecache:
            oldChapters = []
            for c in fs.filecache[n]:
                if time() - fs.filecache[n][c]['timestamp'] > timeout:
                    oldChapters.append(c)

            for c in oldChapters:
                print("Deleting chapter", c, "of", n)
                del fs.filecache[n][c]

            if not len(fs.filecache[n].keys()):
                oldNames.append(n)

        for n in oldNames:
            print("Deleting", n)
            del fs.filecache[n]

        cv.notifyAll()
        cv.release()





workerThreads = []
tasks = Queue()
numThreads = 20

def main(mountpoint, rfile):
    cv = Condition()

    fs = MangaReaderFS(rfile, cv, tasks, mountpoint)

    for i in range(numThreads):
        t = Thread(target=worker, args=(tasks, cv, fs))
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
        print("Usage: \n\tpython3 mangareaderFS.py [mountpoint] [readinglist] (numThreads)\n\n\t\
  where numThreads is optional and defaults to 20\n\t\
  and readinglist is a file containing the manga you want to read\n\t\
   (this can also be updated by creating/deleting files)")
        exit(1)
    if(len(argv)>3):
        numThreads = int(argv[3])
    main(argv[1], argv[2])
