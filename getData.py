import re
import string

from bs4 import BeautifulSoup
from io import BytesIO
from requests import get
from sys import argv

validated_titles = dict()

base_url = "http://www.mangareader.net"
search_url = "http://www.mangareader.net/search/?w="

def _sanitize_title(title):
  alphanumeric = string.ascii_lowercase + string.digits + ' '
  title = title.lower()
  title = "".join(filter(lambda x: x in alphanumeric, title))
  return title

def _encode_name_for_url(name):
  return name.replace(" ", "-")

def _encode_url_name_for_search(name):
  return name.replace("-", "+")

def _get_alternate_names_for_link(link):
     req = get(f"{base_url}/{link}")
     if not req.ok:
         return None

     soup = BeautifulSoup(req.text, 'html.parser')
     text_blocks = list(map(lambda e: e.get_text(), soup.find_all('td')))
     try:
         altnames = text_blocks[text_blocks.index('Alternate Name:') + 1]
         altnames = re.split(',|;', altnames.lower().replace(" ", ""))
         return altnames
     except:
         return None

def _search_for_url_name(manga_name):
    url = search_url + _encode_url_name_for_search(manga_name)
    req = get(url)
    if not req.ok:
        return None

    soup = BeautifulSoup(req.text, 'html.parser')
    links = soup.find_all('div', {"class":"manga_name"})
    if not links:
        return None

    # try/except in case find fails
    try:
        links = map(lambda x: x.find('a').get('href'), links)
    except:
        return None

    links = map(lambda x: x.replace('/', ''), links)
    return links

def _validate_title(title):
    title = _sanitize_title(title)
    if title in validated_titles:
        return validated_titles[title]

    manga_name = _encode_name_for_url(title)
    url = f"{base_url}/{manga_name}"
    req = get(url)
    if req.ok:
        validated_titles[title] = manga_name
        return manga_name

    if not req.status_code == 404:
        return None

    links = _search_for_url_name(manga_name)
    if not links:
      return None

    # Cast to list because we'll need to iterate multiple times
    links = list(links)

     # For each link for all alternate names that links go by so that we can
     # verify that our match isn't just a similar name, but an alternate title
     # of the requested title
    altnames = list(zip(links, map(_get_alternate_names_for_link, links)))
    print(altnames)

    # Account for wonky spacing which mangareader adds sometimes
    # We do this down in the loop with altnames as well
    title_clean = title.replace(" ", "")
    for (link, alts)  in altnames:
        alts = map(lambda x: x.replace(" ", ""), alts)
        if title_clean in alts:
            # Don't store the leading /
            validated_titles[title] = link.replace('/', '')
            return validated_titles[title]

    return None

def _remove_leading_zeros(text):
    return re.match('0*(\d*)', text).group(1)

def getChapters(title):
    title = _validate_title(title)
    if not title:
        return []

    manga_name = _encode_name_for_url(title)
    url = f"{base_url}/{manga_name}"
    req = get(url)
    if not req.ok:
        return []

    soup = BeautifulSoup(req.text, 'html.parser')
    chapterlist = soup.find_all(id='chapterlist')
    if not chapterlist:
        return []

    links = chapterlist[0].find_all('a')
    links = list(map(lambda x: f"{base_url}/{x.get('href')}", links))

    return links

def getPages(title, chapter):
    title = _validate_title(title)
    if not title:
      return 0

    chapter = _remove_leading_zeros(chapter)
    manga_name = _encode_name_for_url(title)
    url = f"{base_url}/{manga_name}/{chapter}"
    req = get(url)
    if not req.ok:
        return 0

    soup = BeautifulSoup(req.text, 'html.parser')
    # This is the drop down menu that lets you select pages
    # Every option in this menu is a page
    menu = soup.find_all('option')
    return len(menu)

def getImage(title, chapter, page):
    title = _validate_title(title)
    if title is None:
        return None

    chapter = _remove_leading_zeros(chapter)
    page = _remove_leading_zeros(page)
    manga_name = _encode_name_for_url(title)

    url = f"{base_url}/{manga_name}/{chapter}/{page}"
    req = get(url)
    soup = BeautifulSoup(req.text, 'html.parser')
    imgurl = ""
    try:
        imgurl = soup.find('div', {'id':'imgholder'}).find('img')['src']
    except:
        return None

    req = get(imgurl)
    if not req.ok:
        return None
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

