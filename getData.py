from requests import get
from re import match, split
from sys import argv
from bs4 import BeautifulSoup
from io import BytesIO

alt_title = dict()

def getChapters(title):
  alphanumeric = 'abcdefghijklmnopqrstuvwxyz 0123456789'
  title = title.lower()
  title = "".join(filter(lambda x: x in alphanumeric, title))

  manga_name = "-".join(title.lower().split(" "))
  url = "http://www.mangareader.net/"+manga_name
  req = get(url)
  
  if not req.ok and req.status_code==404:
    url = "http://www.mangareader.net/search/?w="+manga_name.replace('-', '+')
    req = get(url)
    soup = BeautifulSoup(req.text, 'html.parser')
    links = soup.find_all('div', {"class":"manga_name"})
    links = list(map(lambda x: x.find('a').get('href'), links))
    souplinks = list(map(lambda x: BeautifulSoup(get("http://www.mangareader.net"+x).text, 'html.parser'), links))
    souplinks = list(map(lambda x: x.find_all('td'), souplinks))
    
    names = []
    for i in range(len(souplinks)):
      j = 0
      for j in range(len(souplinks[j])):
        if souplinks[i][j].get_text() == "Alternate Name:":
          j+=1
          break
      names.append(split(',|;', souplinks[i][j].get_text().lower().replace(" ", "")))

    for i in range(len(names)):
      if title.replace(" ", "") in names[i]:
        alt_title[title] = links[i][1:].replace("-", " ")
        title = alt_title[title]
        manga_name = "-".join(title.lower().split(" "))
        url = "http://www.mangareader.net/"+manga_name
        req = get(url)
        break
  if not req.ok:
    return []      

  soup = BeautifulSoup(req.text, 'html.parser')
  links = soup.find_all('a')
  links = list(map(lambda x: x.get_text().lower(), links))
  links = list(map(lambda x: "".join(filter(lambda y: y in alphanumeric, x)),
      links))
  links = list(filter(lambda x: match(title.lower()+" [0-9]+", x), links))

  start = 0
  last = -1
  for l in links:
      chapter = int(l.split(title)[1])
      if last+1 == chapter:
          start -= 1
          break
      else:
          last = chapter
          start += 1
  
  links = links[start:]
  links = list(map(lambda x: url+"/"+str(x+1), range(len(links))))
  return links

def getPages(title, chapter):
  alphanumeric = 'abcdefghijklmnopqrstuvwxyz 0123456789'
  title = title.lower()
  title = "".join(filter(lambda x: x in alphanumeric, title))

  if title in alt_title:
    title = alt_title[title]

  while chapter[0] == '0':
      chapter = chapter[1:]
  manga_name = "-".join(title.split(" "))
  url = "http://www.mangareader.net/"+manga_name+"/"+chapter
  req = get(url)
  soup = BeautifulSoup(req.text, 'html.parser')
  menu = soup.find_all('option')
  return len(menu)

def getImage(title, chapter, page):
  alphanumeric = 'abcdefghijklmnopqrstuvwxyz 0123456789'
  title = title.lower()
  title = "".join(filter(lambda x: x in alphanumeric, title))

  if title in alt_title:
    title = alt_title[title]

  while chapter[0] == '0':
      chapter = chapter[1:]
  while page[0] == '0':
      page = page[1:] 
  manga_name = "-".join(title.split(" "))
  url = "http://www.mangareader.net/"+manga_name+"/"+chapter+"/"+page
  req = get(url)
  req = req.text.split("\n")
  for r in req:
      if "document['pu']" in r:
          url = r.split("'")[3]
          break
  if url=="":
      return "NOT FOUND".encode()
  req = get(url)
  return req.content

if __name__ == '__main__':
  if len(argv)<2:
    print("Please provide a manga name")
  else:
    if len(argv)==2:
      title = argv[1]
      print(getChapters(title))
    elif len(argv)==3:
      title = argv[1]
      chapter = argv[2]
      print(getPages(title, chapter))
    else:
      title = argv[1]
      chapter = argv[2]
      page = argv[3]
      print(getImage(title, chapter, page))

