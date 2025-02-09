#!/usr/bin/env python3
'''
A utility to download podcasts
'''

# TODO: Move the namespace search REGEX string from the config into the script
        # This does not need to be managed by the end user unless they are
        # an advanced user.
# TODO: Add Docstrings and ensure comments are accurate and helpful
# TODO: Syslogging and/or debug messaging
# TODO: Remove print statements
# TODO: Multithreaded downloads
# TODO: Error handling
# TODO: Add type hints to functions

import os
import sys
import re
import time  # TODO: Remove if not needed for dry run workflow? (Sleep)
import xml.etree.ElementTree as ET
from datetime import datetime

import mimetypes
import mutagen
import requests
import yaml


# Set up configuration for the run
script_location = os.path.dirname(os.path.realpath(sys.argv[0]))
with open(f"{script_location}/config.yaml", "r", encoding='utf-8') as cfg:
    config = cfg.read()

config = yaml.safe_load(config)

# Expand out path and append a '/' if not present
config['outPath'] = os.path.expandvars(config["outPath"])
config['outPath'] = os.path.expanduser(config["outPath"])
if config['outPath'][:-1] != '/':
    config['outPath'] += '/'



def extract_date(episode_obj: ET.Element) -> datetime.strptime :
    """
    Extracts the episode publication date from the episode xml.

    Parameters
    ----------

    **episode_obj**: ET.Element -- A string containing individual episode RSS \
        XML
    
    Returns
    -------
    
     **_**: str -- A string representation of the episode publication date.  
    ex. 'Mon, 01 Jan 2000 10:45:21 -0600z'
    """
    date_str = episode_obj.find("pubDate").text
    date_format = "%a, %d %b %Y %H:%M:%S %z"
    return datetime.strptime( date_str, date_format )


def get_rss(xml_location: str) -> str:
    """
    Loads the RSS from an online source or local file if present.

    Parameters
    ----------
    
    - **xml_location**: str -- A string containing a URL or file path location.

    Returns
    -------
    
    - **xml**: str -- A string containing the complete RSS feed xml document \
        location. This can be a URL or local file path.
    """
    if xml_location[0:4] == 'http':
        xml = requests.get(xml_location, timeout=120).content
    else:
        with open(xml_location, encoding='utf-8') as xml_text:
            xml = xml_text.read()
    # Get name spaces
    ns = { x[0]: x[1] for x in re.findall(config['namespaceRegex'], xml.decode("UTF-8")) }

    return xml, ns


def out_date(date_object) -> datetime.strftime:
    """
    Reduces a full date to a reduced form (YYYY-mm-dd).

    Parameters
    ----------
    
    **date_object**: datetime.strptime -- A datetime strptime object.
    
    Returns
    -------
    
    **_**: datetime.strftime -- The shortened date.
    """
    return datetime.strftime( date_object, '%Y-%m-%d')


def date_sort(episode_list: ET.Element) -> ET.Element:
    """
    Sorts all episodes from oldest to newest.
    
    Parameters
    ----------

    **episode_list**: ET.Element -- An XML element containing the list of all RSS \
        episodes

    Returns
    -------

    **_**: ET.Element -- List of episodes in order by date
    """
    return sorted(episode_list, key=extract_date )


def clean_filename(file_str: str) -> str:
    """
    Filter to remove characters that may be problematic in file names.

    Parameters
    ----------
    
    file_str: str -- A string representing the output filename.

    Returns
    -------
    
    str -- The sanitized filename.
    """
    good_character = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
    good_character += "ÀÈÌÒÙÁÉÍÓÚÝÂÊÎÔÛÄËÏÖÜŸÃÑÕÅÆŒÇÐØ"
    good_character += good_character.lower()
    good_character += "1234567890-_.ß"

    # Modify spaces and ":" characters to filename friendly characters
    file_str = re.sub(r"\s+", '_', file_str)

    # String Comprehension! Filter out any other "bad" characters
    return ''.join(lett if lett in good_character else '' for lett in file_str)


def process_podcast(episode_number: int, episode: ET.Element, podcast_config: dict) -> None:
    """
    "Main" function to load RSS feed and download episodes

    Parameters
    ----------

    **episode_number**: int -- A number representing the episode release order
    **episode**: ET.Element -- An XML element holding the information for a \
        single podcast episode.
    **tags**: dict -- any extra tags for the episode. (Default: {})
    """
    # Notes:
    # ID3 Tag List
    # https://exiftool.org/TagNames/ID3.html

    tags = podcast_config['podcast_tags']

    tags['title']            = episode.findtext('title')
    tags['description']      = episode.findtext('description')
    tags['PublicationDate']  = episode.findtext('pubDate')
    tags['date']             = extract_date(episode)
    tags['rawURL']           = episode.find('enclosure').get('url')
    tags['genre']            = 'Podcast'
    tags['extension']        = mimetypes.guess_extension(
                                    episode.find('enclosure').get('type')
                                )
    print(f'Working on {tags["title"]}')

    # Prepare date for filename
    date_string = out_date(tags['date'])
    tags['dateYear'] = str(tags['date'].year)

    # Build Filename
    filename = clean_filename(f"{date_string}_ep{episode_number}_"
                              f"{tags['title']}{tags['extension']}"
                            )
    full_path = f'{podcast_config["outDir"]}{filename}'

    # Get Download URL
    try:
        match_string = re.compile(podcast_config['episodeUrlFilter'])
        processed_url = match_string.findall(tags['rawURL'])[0]
    except KeyError:
        processed_url = tags['rawURL']

    if not os.path.exists(full_path) and not config['dryRun']:
        # Download episode art if present
        try:
            episode_art_url = episode.find('.//itunes:image',
                                        namespaces=podcast_config['namespaces']
                                        ).get('href')
        except AttributeError:
            print('No Episode Art Found!')
            episode_art_url = None

        if episode_art_url:
            try:
                match_string = re.compile(podcast_config['artUrlFilter'])
                processed_art_url = match_string.findall(episode_art_url)[0]
            except KeyError:
                processed_art_url = episode_art_url
            eart = requests.get(processed_art_url, timeout=30)
            tags['episode_art']      = eart.content
            tags['episode_art_mime'] = eart.headers['Content-Type']
        else:
            tags['episode_art']      = tags['art']
            tags['episode_art_mime'] = tags['artMime']

        tags['episode_art_ext']  = mimetypes.guess_extension(
                                        tags['episode_art_mime'])

        # Download Episode
        print(f'Downloading {filename}')
        html = requests.get(processed_url, timeout=30)

        # Save Episode to file
        print(f'Saving {filename}')
        with open(full_path, 'wb') as f:
            f.write(html.content)

        # Update Metadata
        tag_file = mutagen.File(full_path)

        # print('\nInitial Tags')
        # for tag in tag_file.tags.items():
        #     if tag[0][:-1] == 'APIC':
        #         print(tag[0])
        #     else:
        #         print(tag)

        tag_file['TRCK'] = mutagen.id3.TRCK(encoding=3, text=str(episode_number))
        tag_file['TIT2'] = mutagen.id3.TIT2(encoding=3, text=tags["title"])
        tag_file['TALB'] = mutagen.id3.TALB(encoding=3, text=tags["album"])
        tag_file['TCOP'] = mutagen.id3.TCOP(encoding=3, text=tags["copyright"])
        tag_file['TPE1'] = mutagen.id3.TPE1(encoding=3, text=tags["artist"])
        tag_file['TPE2'] = mutagen.id3.TPE2(encoding=3, text=tags["album_artist"])
        tag_file['TCON'] = mutagen.id3.TCON(encoding=3, text=tags["genre"])
        tag_file['TDRC'] = mutagen.id3.TDRC(encoding=3, text=tags["dateYear"])

        tag_file['APIC:'] = mutagen.id3.APIC(
            data=tags["episode_art"],
            type=mutagen.id3.PictureType.COVER_FRONT,
            # desc="cover",
            mime=tags["episode_art_mime"])

        # print('\nFinal Tags')
        # for tag in tag_file.tags.items():
        #     if tag[0][:-1] == 'APIC':
        #         print(tag[0])
        #     else:
        #         print(tag)

        tag_file.save()

    elif config['dryRun']:
        print('Executing dry run, sleeping 0.1 second.')
        time.sleep(0.1)

    else:
        print('Episode already downloaded. Skipping...')
        print(f'\t    Track: {episode_number}')
        print(f'\tFile name: {filename}')


def main() -> None:
    """
    Main setup function for rest of the application.
    """
    for i, podcast in enumerate(config['podList']):
        print(f'Starting podcast {i+1}, "{podcast["name"]}"')

        podcast_config = {}
        podcast_config.update(podcast)
        podcast_config['outDir'] = f"{config['outPath']}{podcast_config['name']}/"

        if not os.path.isdir(podcast_config['outDir']):
            os.makedirs(podcast_config['outDir'], exist_ok = True)

        rss_xml, ns = get_rss(podcast_config['rssFeedUrl'])
        root = ET.fromstring(rss_xml)

        r = requests.get(
                        url=root.find('./channel/image/url').text,
                        timeout=10
                    )

        podcast_config['episodes'] = date_sort(root.findall('./channel/item'))
        podcast_config['namespaces'] = ns
        podcast_config['podcast_tags'] = {
            'album': root.findtext('./channel/title'),
            'art': r.content,
            'artMime': r.headers['Content-Type'],
            'artist': root.findtext(".//itunes:author", namespaces=ns),
            'album_artist': root.findtext('./channel/title'),
            'copyright': root.findtext('./channel/copyright'),
        }

        ext = mimetypes.guess_extension(podcast_config['podcast_tags']['artMime'])
        out_path = f'{podcast_config["outDir"]}cover{ext}'

        # Save a copy of the album art
        with open(out_path, 'wb') as f:
            f.write(podcast_config['podcast_tags']['art'])

        # for episode in root.findall('./channel/item'):
        for i,episode in enumerate(podcast_config['episodes'], start=1):
            process_podcast(i, episode, podcast_config)


if __name__ == '__main__':
    main()
