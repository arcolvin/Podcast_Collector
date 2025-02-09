#!/usr/bin/env python3


import requests
import re
import os
import xml.etree.ElementTree as ET
from datetime import datetime
import time     # TODO: Remove if not needed for dry run? (Sleep)
import mutagen


global envCfg
envcfg = {
    'dryRun': False,
    'outPath': os.path.expanduser('~/Downloads/Podcast/')
}

# TODO: Multithreaded downloads
# TODO: Functionalize!
# TODO: Error handling
# TODO: Syslogging and/or debug messaging

# ID3 Tag List
# https://exiftool.org/TagNames/ID3.html

def extractDate(episodeObj):
    dateStr = episodeObj.find('pubDate').text
    dateFormat = '%a, %d %b %Y %H:%M:%S %z'
    return datetime.strptime( dateStr, dateFormat )

def getRSS(url):
    if url[0:4] == 'http':
        xml = requests.get(url).content
    else:
        with open(url) as f:
            xml = f.read()
    return xml


def outDate(dateObj):
    return datetime.strftime( dateObj, '%Y-%m-%d')


def dateSort(epList):
   return sorted(epList, key=extractDate )


def cleanFilename(fileStr):
    return fileStr.replace(' ','_')\
        .replace('/', '').replace('\\', '').replace('?','').replace("'",'')\
        .replace('"','').replace('!','').replace('@','').replace('#','')\
        .replace('$','').replace('%','').replace('^','').replace('&','')\
        .replace('*','').replace('(','').replace(')','').replace('=','')\
        .replace('+','').replace('{','').replace('}','').replace('[','')\
        .replace(']','').replace('|','').replace(':','').replace(';','')\
        .replace('<','').replace('>','').replace(',','').replace('"','')\
        .replace("'",'')


# TODO: Break this function up
def podProcess (epNum, episode, tags={}):
    # tags = {'album':album, 'art':albumArtImage, 'artist':artist}

    tags['title']           = episode.find('title').text
    tags['description']     = episode.find('description').text
    tags['PublicationDate'] = episode.find('pubDate').text
    tags['date']            = extractDate(episode)
    tags['rawURL']          = episode.find('enclosure').items()[2][1]
    tags['genre']           = 'Podcast'

    print(f'Working on {tags["title"]}')

    # Prepare date for filename
    dateString = outDate(tags['date'])
    tags['dateYear'] = str(tags['date'].year)

    # Build Filename
    filename = cleanFilename(f'{dateString}_ep{epNum}_{tags["title"]}.mp3')
    fullPath = os.path.expanduser(f'{envcfg["outPath"]}{filename}')

    # Get Download URL
    matchString = re.compile(r'(.*?)\?')
    processedURL = matchString.findall(tags['rawURL'])[0]

    if not os.path.exists(fullPath) and not envcfg['dryRun']:
        # Download
        # Download Episode
        print(f'Downloading {filename}')
        html = requests.get(processedURL)
        
        # Save Episode to file
        print(f'Saving {filename}')
        with open(fullPath, 'wb') as f:
            f.write(html.content)

        # TODO: Not all of the metadata is updating as expected.
        #       Some album art is not loading as expected either (also does not show up in tagger)
        #       Missing artist and album even though it should be updated here...

        # Update Metadata
        tagFile = mutagen.File(fullPath)

        print('\nInitial Tags')
        for tag in tagFile.tags.items():
            if tag[0][:-1] == 'APIC':
                print(tag[0])
            else:
                print(tag)

        tagFile['TRCK'] = mutagen.id3.TRCK(encoding=3, text=str(epNum))
        tagFile['TIT2'] = mutagen.id3.TIT2(encoding=3, text=tags["title"])
        tagFile['TALB'] = mutagen.id3.TALB(encoding=3, text=tags["album"])
        tagFile['TCOP'] = mutagen.id3.TCOP(encoding=3, text=tags["artist"])
        tagFile['TPE1'] = mutagen.id3.TPE1(encoding=3, text=tags["artist"])
        tagFile['TPE2'] = mutagen.id3.TPE2(encoding=3, text=tags["artist"])
        tagFile['TCON'] = mutagen.id3.TCON(encoding=3, text=tags["genre"])
        tagFile['TDRC'] = mutagen.id3.TDRC(encoding=3, text=tags["dateYear"])
        
        tagFile['APIC:'] = mutagen.id3.APIC(
            data=tags["art"],
            type=mutagen.id3.PictureType.COVER_FRONT,
            # desc="cover",
            mime="image/jpeg")

        print('\nFinal Tags')
        for tag in tagFile.tags.items():
            if tag[0][:-1] == 'APIC':
                print(tag[0])
            else:
                print(tag)

        tagFile.save()

    elif envcfg['dryRun']:
        print('Executing dry run, sleeping 1 second.')
        time.sleep(1)

    else:
        print('Episode already downloaded. Skipping...')
        print(f'\t    Track: {i}')
        print(f'\tFile name: {filename}')


if __name__ == '__main__':

    if not os.path.isdir(envcfg['outPath']):
        os.makedirs(envcfg['outPath'], exist_ok = True)

    rssXML = getRSS('https://feeds.simplecast.com/PxEW_ipK')

    root = ET.fromstring(rssXML)

    episodes = dateSort(root.findall('./channel/item'))

    albumArtURL = root.find('./channel/image/url').text

    initTag = {'album': root.find('./channel/title').text,
               'art': requests.get(albumArtURL).content,
               'artist': root.find('./channel/copyright').text[5:]
    }


    # Save a copy of the album art
    with open(f'{envcfg["outPath"]}/coverArt.jpg', 'wb') as f:
        f.write(initTag['art'])

    # for episode in root.findall('./channel/item'):
    for i,episode in enumerate(episodes, 1):
        podProcess(i, episode, initTag)
