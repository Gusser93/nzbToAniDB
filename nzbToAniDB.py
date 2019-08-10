#!/usr/bin/python

# Author: Benjamin Waller <benjamin@mycontact.eu>
# Mod by Markus Vieth <vieth.m@gmx.de>
# based on pyanidb

##############################################################################
### NZBGET POST-PROCESSING SCRIPT                                          ###
# Anime renaming & sync with AniDB.net
#
# This script will rename Anime files after syncing with AniDB.
# Renaming can be done using AniDB or TheTVDB as source.
#
#
# NOTE: Edit "anidb.cfg" in your scripts folder to configure nzbToAniDB
#
#
# NOTE: This script requires Python to be installed on your system.
### NZBGET POST-PROCESSING SCRIPT                                          ###
##############################################################################
import optparse, os, sys, getpass, shutil, urllib, time, json
from pathlib import Path
from collections import deque
import anidb, anidb.hash
import tvdb
from datetime import datetime
import configparser
import unicodedata, string



validFilenameChars = list("-_.;()[]`'! %s%s" % (string.ascii_letters, string.digits))
def remove_disallowed_filename_chars(filename):
    cleanedFilename = unicodedata.normalize('NFKD', str(filename))#.encode('ASCII', 'ignore')
    return ''.join([c for c in cleanedFilename if c in validFilenameChars])

class Options:
    def __init__(self, config):
        self.username = config["AniDB"].get("username", None)
        self.password = config["AniDB"].get("password", None)
        self.recursive = config["AniDB"].getboolean("recursiv", True)
        self.suffix = [s.lower() for s in config["AniDB"].get("suffix", "avi ogm mkv mp4 wmv m4v").split(" ")]
        self.cache = config["AniDB"].getboolean("cache", True)
        self.tvdb = config["AniDB"].getboolean("tvdb", False)
        self.multihash = config["AniDB"].getboolean("multihash", False)
        self.identify = config["AniDB"].getboolean("identify", False)
        self.add = config["AniDB"].getboolean("add", False)
        self.watched = config["AniDB"].getboolean("watched", False)
        self.rename = config["AniDB"].getboolean("rename", False)
        self.move = config["AniDB"].getboolean("move", False)
        self.delete = config["AniDB"].getboolean("delete", False)
        self.directory = Path(config["AniDB"].get("directory", None))
        self.directorymovie = Path(config["AniDB"].get("directorymovie", None))
        self.update = config["AniDB"].getboolean("update", False)
        self.color = config["AniDB"].getboolean("color", True)
        self.login = False
        
def get_files(paths):
    files = []
    remaining = deque(paths)
    while remaining:
        name = remaining.popleft()
        if not os.access(name, os.R_OK):
            print('{0} {1}'.format(red('Invalid file:'), name))
        elif name.is_file():
            files.append(name)
        elif name.is_dir():
            if not options.recursive:
                print('{0} {1}'.format(red('Is a directory:'), name))
            else:
                for sub in name.iterdir():
                    if os.name == "posix" and sub.parts[-1].startswith('.'):
                        continue
                    if sub.is_file() and sub.suffix[1:].lower() in options.suffix:
                        files.append(sub)
                    elif sub.is_dir():
                        remaining.appendleft(sub)

    if not files:
        print(blue('Nothing to do.'))
        sys.exit(0)
    return files

def login():
    a = anidb.AniDB(options.username, options.password)
    try:
        a.auth()
        print('{0} {1}'.format(blue('Logged in as user:'), options.username))
    except anidb.AniDBUserError:
        print(red('Invalid username/password.'))
        sys.exit(0)
    except anidb.AniDBTimeout:
        print(red('Connection timed out.'))
        sys.exit(0)
    except anidb.AniDBError as e:
        print('{0} {1}'.format(red('Fatal error:'), e))
        sys.exit(0)
    return a

def hashing():
    hashed = unknown = 0
    for file in anidb.hash.hash_files(files, options.cache, (('ed2k', 'md5', 'sha1', 'crc32') if options.multihash else ('ed2k',))):
        print('{0} ed2k://|file|{1}|{2}|{3}|{4}'.format(blue('Hashed:'),  file.name, file.size, file.ed2k, ' (cached)' if file.cached else ''))
        fid = (file.size, file.ed2k)
        hashed += 1

        try:

            # Multihash.
            if options.multihash:
                print('{0} {1}'.format(blue('MD5:'), file.md5))
                print('{0} {1}'.format(blue('SHA1:'), file.sha1))
                print('{0} {1}'.format(blue('CRC32:'), file.crc32))

            # Identify.

            if options.identify:
                info = a.get_file(fid, True)
                fid = int(info['fid'])

                if (info['english'] == ""): info['english'] = info['romaji']

                print('{0} [{1}] {2} ({3}) - {4} - {5} ({6})'.format(green('Identified:'), info['gtag'], info['romaji'], info['english'], info['epno'], info['epromaji'], info['epname']))

            # get tvdb info

            if options.tvdb:
                tvdbinfo = mytvdb.find_tvdb(info["aid"],info["epno"])
                if tvdbinfo:
                    info.update(tvdbinfo)
                    print('{0} {1} S{2} E{3} - {4}'.format(green('TvDB:'), info['tvdbseriesname'].encode('utf-8'), info['tvdbseason'], info['tvdbepnum'][0] if len(info['tvdbepnum']) == 1 else info['tvdbepnum'][0]+"-"+info['tvdbepnum'][len(info['tvdbepnum'])-1], info['tvdbepname'].encode('utf-8')))
                else:
                    print(red('TVDB: ') + 'no match found!')

            # Renaming.

            if options.rename or options.move:
                rename = config["rename"]

                if options.rename:

                    if options.tvdb and tvdbinfo:
                        s = rename['tvdbepisodeformat']
                    elif (info['type'] == 'Movie' and rename['movieformat']):
                        s = rename['movieformat']
                    elif (info['type'] == 'OVA' and rename['ovaformat']):
                        s = rename['ovaformat']
                    elif (rename['tvformat']):
                        s = rename['tvformat']
                    else:
                        s = '%ATe% - %EpNo%%Ver% - %ETe% [%GTs%][%FCRC%]'

                    rename_data = {
                        #Anime title, r: romaji, e: english, k: kanji, s: synonym, o: other
                        'ATr': info['romaji'],
                        'ATe': info['english'],
                        'ATk': info['kanji'],
                        #'ATs': info['synonym'],
                        #'ATo': info['other'],

                        #Episode title, languages as above
                        'ETr': info['epromaji'],
                        'ETe': info['epname'],
                        'ETk': info['epkanji'],

                        #Group title, s: short, l: long
                        'GTs':info['gtag'],
                        'GTl':info['gname'],

                        'EpHiNo': info['eptotal'], #Highest (subbed) episode number
                        'EpCount': info['eptotal'], #Anime Episode count
                        'AYearBegin': info['year'].split("-")[0],
                        'AYearEnd':	 info['year'].split("-")[1] if (info['year'].find('-') > 0) else '', #The beginning & ending year of the anime
                        #'ACatList': info['category'],

                        'EpNo': info['epno'] if (len(info['epno']) > 1) else '0' + info['epno'], #File's Episode number

                        'Type': info['type'], #Anime type, Value: 'Movie', 'TV', 'OVA', 'Web'
                        'Depr': info['depr'], #File is deprecated if the value is '1'
                        'Cen': {0:'',128:'censored'}[(int(info['state']) & 128)], #File is censored
                        'Ver': {0: '', 4: 'v2', 8: 'v3', 16: 'v4', 32: 'v5'}[(int(info['state']) & 0x3c)], #File version
                        'Source': info['source'], #Where the file came from (HDTV, DTV, WWW, etc)
                        'Quality': info['quality'], #How good the quality of the file is (Very Good, Good, Eye Cancer)
                        #'AniDBFN': info['anifilename'], #Default AniDB filename
                        'CurrentFN': file.name.name, #Current Filename
                        'FCrc' : info['crc32'],#The file's crc
                        'FCRC': info['crc32'].upper(),
                        'FVideoRes': info['vres'], #Video Resolution (e.g. 1920x1080)
                        'FALng': info['dublang'], #List of available audio languages (japanese, english'japanese'german)
                        'FSLng': info['sublang'], #List of available subtitle languages (japanese, english'japanese'german)
                        'FACodec': info['acodec'], #Codecs used for the Audiostreams
                        'FVCodec': info['vcodec'], #Codecs used for the Videostreams
                        'suf': info['filetype'],
                    }

                    if options.tvdb and tvdbinfo:
                        rename_data.update({	
                            #tvdb
                            'TSTe': info['tvdbseriesname'],
                            'TETe': info['tvdbepname'],
                            'TS': info['tvdbseason'],
                            'TE': info['tvdbepnum'][0] if len(info['tvdbepnum']) == 1 else info['tvdbepnum'][0]+"-"+info['tvdbepnum'][len(info['tvdbepnum'])-1],
                            'TSE': 'S'+info['tvdbseason']+'E'+info['tvdbepnum'][0] if len(info['tvdbepnum']) == 1 else 'S'+info['tvdbseason']+'E'+info['tvdbepnum'][0]+"-E"+info['tvdbepnum'][len(info['tvdbepnum'])-1],
                        })

                    # parse s to replace tags
                    #for name, value in rename.items():
                    #	s = s.replace(r'%' + name + r'%', value)

                    for name, value in rename_data.items():
                        s = s.replace(r'%' + name + r'%', value)

                    s = s + '.' + rename_data['suf']

                    # change spaces to underscores, if first character in s is an underscore
                    if s[0] == '_':
                        s = s[1:].replace(' ', '_')

                if options.move:

                    if options.tvdb and tvdbinfo:
                        f = rename['tvdbfoldername']
                        if int(info['tvdbseason']) > 0:
                            fs = rename['tvdbseasonfolder']
                        else:
                            fs = rename['tvdbspecialsfolder']
                    elif (info['type'] == "Movie" and rename['foldernamemovie']):
                        f = rename['foldernamemovie']
                        fs = None
                    elif (rename['foldername']):
                        f = rename['foldername']
                        fs = None
                    else:
                        f = '%ATe%'
                        fs = None

                    move_data = {
                        #Anime title, r: romaji, e: english, k: kanji, s: synonym, o: other
                        'ATr': info['romaji'],
                        'ATe': info['english'],
                        'ATk': info['kanji'],
                        #'ATs': info['synonym'],
                        #'ATo': info['other'],

                        #Group title, s: short, l: long
                        'GTs':info['gtag'],
                        'GTl':info['gname'],

                        'EpHiNo': info['eptotal'], #Highest (subbed) episode number
                        'EpCount': info['eptotal'], #Anime Episode count
                        'AYearBegin': info['year'].split("-")[0],
                        'AYearEnd':	 info['year'].split("-")[1] if (info['year'].find('-') > 0) else '', #The beginning & ending year of the anime
                        #'ACatList': info['category'],

                        'Type': info['type'], #Anime type, Value: 'Movie', 'TV', 'OVA', 'Web'
                        'Source': info['source'], #Where the file came from (HDTV, DTV, WWW, etc)
                        'Quality': info['quality'], #How good the quality of the file is (Very Good, Good, Eye Cancer)
                        'FVideoRes': info['vres'], #Video Resolution (e.g. 1920x1080)
                        'FALng': info['dublang'], #List of available audio languages (japanese, english'japanese'german)
                        'FSLng': info['sublang'], #List of available subtitle languages (japanese, english'japanese'german)
                        'FACodec': info['acodec'], #Codecs used for the Audiostreams
                        'FVCodec': info['vcodec'], #Codecs used for the Videostreams
                        'suf': info['filetype']}

                    if options.tvdb and tvdbinfo:
                        move_data.update({	
                            #tvdb
                            'TSTe': info['tvdbseriesname'],
                            'TETe': info['tvdbepname'],
                            'TS': info['tvdbseason'],
                            'TE': info['tvdbepnum'][0] if len(info['tvdbepnum']) == 1 else info['tvdbepnum'][0]+"-"+info['tvdbepnum'][len(info['tvdbepnum'])-1],
                            'TSE': 'S'+info['tvdbseason']+'E'+info['tvdbepnum'][0] if len(info['tvdbepnum']) == 1 else 'S'+info['tvdbseason']+'E'+info['tvdbepnum'][0]+"-E"+info['tvdbepnum'][len(info['tvdbepnum'])-1],
                        })

                    # parse f to replace tags
                    #for name, value in rename.items():
                    #	f = f.replace(r'%' + name + r'%', value)

                    for name, value in move_data.items():
                        f = f.replace(r'%' + name + r'%', value)

                    if fs:
                        for name, value in move_data.items():
                            fs = fs.replace(r'%' + name + r'%', value)

                    # change spaces to underscores, if first character in s is an underscore
                    if f[0] == '_':
                        f = f[1:].replace(' ', '_')
                    if fs and fs[0] == '_':
                        fs = fs[1:].replace(' ', '_')

                #do the rename and move

                filename = file.name.name

                if options.rename:
                    filename = remove_disallowed_filename_chars(s)

                    while filename.startswith('.'):
                        filename = filename[1:]
                    print('{0} {1}'.format(yellow('Renaming to:'), filename))

                    path = file.name.parent

                if options.move:
                    subdir = remove_disallowed_filename_chars(f)
                    while subdir.startswith('.'):
                        subdir = subdir[1:]

                    if (options.directorymovie and info['type'] == 'Movie'):
                        target_directory = options.directorymovie
                    else:
                        target_directory = options.directory

                    basedir = target_directory / subdir
                    
                    if not basedir.exists():
                        basedir.mkdir(parents=True, exist_ok=True)

                    if fs:
                        seasondir = remove_disallowed_filename_chars(fs)
                        while seasondir.startswith('.'):
                            seasondir = seasondir[1:]
                        subdir = subdir / seasondir

                    path = target_directory / subdir

                    print('{0} {1}'.format(yellow('Moving to:'), path))
                    if (not path.exists()):
                        path.mkdir()
                        #oldumask = os.umask(000)
                        #os.makedirs(path)
                        #os.umask(oldumask)


                target = path / filename
                #failsave against long filenames
                #if len(target) > 255:
                #    target = target[:250].strip() + target[-4:]

                shutil.move(file.name, target)

            if options.delete:
                delete_folder = True
                folder = file.name.parent
                for sub in folder.iterdir():
                    if sub.exists():
                        #don't delete
                        delete_folder = False

                if delete_folder:
                    folder.rmdir()


            # Adding.

            if options.add:
                a.add_file(fid, viewed = options.watched, retry = True)
                print(green('Added to mylist.'))

            # Watched.

            elif options.watched:
                a.add_file(fid, viewed = True, edit = True, retry = True)
                print(green('Marked watched.'))

        except anidb.AniDBUnknownFile:
            print(red('Unknown file.'))
            unknown += 1

        except anidb.AniDBNotInMylist:
            print(red('File not in mylist.'))
    return hashed, unknown

if __name__ == "__main__":
    config = {}
    args = sys.argv
    try:
        config = configparser.ConfigParser(interpolation=None)
        config.read(Path(".", "anidb.cfg"))
    except:
        pass

    target_path = list(map(Path, args[1:]))

    if not all(p.exists() for p in target_path):
        print('Destination directory does not exist')
        sys.exit(1)
    
    options = Options(config)
    
    # Colors.
    if options.color:
        red    = lambda x: '\x1b[1;31m{}\x1b[0m'.format(x)
        green  = lambda x: '\x1b[1;32m{}\x1b[0m'.format(x)
        yellow = lambda x: '\x1b[1;33m{}\x1b[0m'.format(x)
        blue   = lambda x: '\x1b[1;34m{}\x1b[0m'.format(x)
    else:
        red    = lambda x: x
        green  = lambda x: x
        yellow = lambda x: x
        blue   = lambda x: x
    
    # Defaults.
    if options.cache:
        try:
            import xattr
        except ImportError:
            print(red('No xattr, caching disabled.'))
            options.cache = False
    options.identify = options.identify or options.rename or options.move or options.tvdb
    options.login = options.add or options.watched or options.identify

    if options.login:
        if not options.username:
            options.username = input('Username: ')
        if not options.password:
            options.password = getpass.getpass()

    if not options.directory and options.move:
        print(red('No target directory.'))
        sys.exit(1)

    if not options.move and options.delete:
        print(red('Can\'t delete folder without moving files.'))
        sys.exit(1)

    if options.tvdb:
        animelistfile = Path(__file__).parent / "anime-list.xml"
        mytvdb = tvdb.TvDB(animelistfile)

    files = get_files(target_path)

    if options.login:
        a = login()
    
    hashed, unknown = hashing()
    
    # notify PlexMediaServer

    if options.update and hashed > 0 and hashed > unknown:

        plex = {}
        try:
            cp = ConfigParser.ConfigParser()
            cp.read(os.path.join(os.path.dirname(sys.argv[0]), "..", "anidb.cfg"))
            for option in cp.options('plex'):
                plex[option] = cp.get('plex', option)

            if (plex['host'] != ""):
                if (plex["sections"] == ""):
                    plex["sections"] = "all"

                for section in plex["sections"].split(","):
                    req = "http://"+plex["host"]+":32400/library/sections/"+section+"/refresh"
                    try:
                        urllib.urlopen(req)
                    except urllib.HTTPError as e:
                        print(red('Could not notify Plex Media Server'))
                        print(e.code)
                    else:
                        print(green('Notified Plex Media Server'))
        except:
            pass
        
    # notify XBMC

    if options.update and hashed > 0 and hashed > unknown:
        xbmc = {}
        try:
            cp = ConfigParser.ConfigParser()
            cp.read(os.path.join(os.path.dirname(sys.argv[0]), "..", "anidb.cfg"))
            for option in cp.options('xbmc'):
                xbmc[option] = cp.get('xbmc', option)

            if (xbmc['host'] != ""):
                if (xbmc['path'] != "" and hashed == 1):
                    updateCommand = '{"jsonrpc":"2.0","method":"VideoLibrary.Scan","params":{"directory":%s},"id":1}' % json.dumps(xbmc['path'] + f + '/')
                    req = 'http://'+xbmc['user']+':'+xbmc['password']+'@'+xbmc['host']+':'+xbmc['port']+'/jsonrpc?request='+urllib.quote(updateCommand,'')
                else:
                    req = "http://"+xbmc["user"]+":"+xbmc["password"]+"@"+xbmc["host"]+":"+xbmc["port"]+"/jsonrpc?request={\"jsonrpc\":\"2.0\",\"method\":\"VideoLibrary.Scan\"}"
                try:
                    urllib.urlopen(req)
                except urllib.HTTPError as e:
                    print(red('Could not notify XBMC'))
                    print(e.code)
                else:
                    print(green('Notified XBMC'))
        except:
            pass
    
    # Finished.
    print(blue('Hashed {0} files{1}.'.format(hashed, ', {0} unknown'.format(unknown) if unknown else '')))
    if (unknown > 0):
        sys.exit(1)
        