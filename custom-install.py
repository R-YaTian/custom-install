#!/usr/bin/env python3

# This file is a part of custom-install.py.
#
# Copyright (c) 2019 Ian Burgwin
# This file is licensed under The MIT License (MIT).
# You can find the full license text in LICENSE.md in the root of this project.

from argparse import ArgumentParser
from os import makedirs, scandir
from os.path import dirname, join
from random import randint
from hashlib import sha256
from sys import exit, platform
from tempfile import TemporaryDirectory
from typing import BinaryIO
import subprocess
import shutil

from pyctr.crypto import CryptoEngine, Keyslot
from pyctr.types.cia import CIAReader, CIASection
from pyctr.types.ncch import NCCHSection
from pyctr.util import roundup

# used to run the save3ds_fuse binary next to the script
script_dir: str = dirname(__file__)

# missing contents are replaced with 0xFFFFFFFF in the cmd file
CMD_MISSING = b'\xff\xff\xff\xff'

# the size of each file and directory in a title's contents are rounded up to this
TITLE_ALIGN_SIZE = 0x8000

# size to read at a time when copying files
READ_SIZE = 0x200000


def copy_with_progress(src: BinaryIO, dst: BinaryIO, size: int, path: str):
    left = size
    cipher = crypto.create_ctr_cipher(Keyslot.SD, crypto.sd_path_to_iv(path))
    while left > 0:
        to_read = min(READ_SIZE, left)
        data = cipher.encrypt(src.read(READ_SIZE))
        dst.write(data)
        left -= to_read
        total_read = size - left
        print(f' {(total_read / size) * 100:>5.1f}%  {total_read / 1048576:>.1f} MiB / {size / 1048576:.1f} MiB',
              end='\r', flush=True)
    print()


parser = ArgumentParser(description='Manually install a CIA to the SD card for a Nintendo 3DS system.')
parser.add_argument('-m', '--movable', help='movable.sed file', required=True)
parser.add_argument('-b', '--boot9', help='boot9 file')
parser.add_argument('--sd', help='path to SD root')
parser.add_argument('--skip-contents', help="don't add contents, only add title info entry", action='store_true')
parser.add_argument('-c', '--cias', help="CIA Files Path")

args = parser.parse_args()

# set up the crypto engine to encrypt contents as they are written to the SD
crypto = CryptoEngine(boot9=args.boot9)
crypto.setup_sd_key_from_file(args.movable)

# try to find the path to the SD card contents
print('Finding path to install to...')
sd_path = join(args.sd, 'Nintendo 3DS', crypto.id0.hex())
id1s = []
for d in scandir(sd_path):
    if d.is_dir() and len(d.name) == 32:
        try:
            id1_tmp = bytes.fromhex(d.name)
        except ValueError:
            continue
        else:
            id1s.append(d.name)

# check the amount of id1 directories
if len(id1s) > 1:
    exit(f'There are multiple id1 directories for id0 {crypto.id0.hex()}, please remove extra directories')
elif len(id1s) == 0:
    exit(f'Could not find a suitable id1 directory for id0 {crypto.id0.hex()}')

sd_path = join(sd_path, id1s[0])

title_info_entries = {}
# for use with a finalize program on the 3DS
finalize_entries = []

filearray = []
fname = []
cia_path = args.cias
dsiware = 0
firm = 0

print('Add CIA files to list...')

try:
    flist = os.listdir(cia_path)
    for fileNAME in flist:
        if os.path.splitext(fileNAME)[1] == '.cia':
            filearray.append(fileNAME )
    ge = len(filearray)
    for i in range(ge):
        fname.append(cia_path + "\\" + filearray[i])
    if ge != 0:
        print("%d CIAs" % len(filearray))
    if ge == 0:
        print("Error: No CIA files")
        exit()
except:
    exit(f'Error: Failed to add CIA files')

for time, c in enumerate(fname):
    # parse the cia
    print('Reading CIA...')
    try:
        cia = CIAReader(c)
    except:
        print('The CIA file maybe a firm, you should install it via FBI or BigBlueMenu')
        firm += 1
        if time != len(fname) - 1:
            continue
        else:
            if ge > (dsiware + firm):
                continue
            else:
                exit()
    tid_parts = (cia.tmd.title_id[0:8], cia.tmd.title_id[8:16])
    tid1 = cia.tmd.title_id[0:8]
    if tid1 == '00048004' or tid1 == '00048015' or tid1 == '00048005'or tid1 == '0004800f':
        print('This is a DSiWare, no point to install it')
        dsiware += 1
        if time != len(fname) - 1:
            continue
        else:
            if ge > (dsiware + firm):
                continue
            else:
                exit()
    try:
        print(f'Installing {cia.contents[0].exefs.icon.get_app_title().short_desc}...')
    except:
        print('Installing...')

    # this includes the sizes for all the files that would be in the title, plus each directory
    #   except the separate directories for DLC contents, which don't count towards the size.
    # five "1"s are here for the tidlow and content directories, the cmd file and its directory, and the tmd file
    sizes = [1] * 5

    if cia.tmd.save_size:
        # one for the data directory, one for the 00000001.sav file
        sizes.extend((1, cia.tmd.save_size))

    for record in cia.content_info:
        sizes.append(record.size)

    # this calculates the size to put in the Title Info Entry
    title_size = sum(roundup(x, TITLE_ALIGN_SIZE) for x in sizes)

    # checks if this is dlc, which has some differences
    is_dlc = tid_parts[0] == '0004008c'

    # this checks if it has a manual (index 1) and is not DLC
    has_manual = (not is_dlc) and (1 in cia.contents)

    # this gets the extdata id from the extheader, stored in the storage info area
    try:
        with cia.contents[0].open_raw_section(NCCHSection.ExtendedHeader) as e:
            e.seek(0x200 + 0x30)
            extdata_id = e.read(8)
    except KeyError:
        # not an executable title
        extdata_id = b'\0' * 8

    # cmd content id, starts with 1 for non-dlc contents
    cmd_id = len(cia.content_info) if is_dlc else 1
    cmd_filename = f'{cmd_id:08x}.cmd'

    # get the title root where all the contents will be
    title_root = join(sd_path, 'title', *tid_parts)
    content_root = join(title_root, 'content')
    # generate the path used for the IV
    title_root_cmd = f'/title/{"/".join(tid_parts)}'
    content_root_cmd = title_root_cmd + '/content'

    makedirs(join(content_root, 'cmd'), exist_ok=True)
    if cia.tmd.save_size:
        makedirs(join(title_root, 'data'), exist_ok=True)
    if is_dlc:
        # create the separate directories for every 256 contents
        for x in range(((len(cia.content_info) - 1) // 256) + 1):
            if os.path.exists(join(content_root, f'{x:08x}')):
                shutil.rmtree(join(content_root, f'{x:08x}'))
            makedirs(join(content_root, f'{x:08x}'))

    # maybe this will be changed in the future
    tmd_id = 0

    tmd_filename = f'{tmd_id:08x}.tmd'

    if not args.skip_contents:
        # write the tmd
        enc_path = content_root_cmd + '/' + tmd_filename
        print(f'Writing {enc_path}...')
        with cia.open_raw_section(CIASection.TitleMetadata) as s, open(join(content_root, tmd_filename), 'wb') as o:
            copy_with_progress(s, o, cia.sections[CIASection.TitleMetadata].size, enc_path)

        # write each content
        for c in cia.content_info:
            content_filename = c.id + '.app'
            if is_dlc:
                dir_index = format((c.cindex // 256), '08x')
                enc_path = content_root_cmd + f'/{dir_index}/{content_filename}'
                out_path = join(content_root, dir_index, content_filename)
            else:
                enc_path = content_root_cmd + '/' + content_filename
                out_path = join(content_root, content_filename)
            print(f'Writing {enc_path}...')
            with cia.open_raw_section(c.cindex) as s, open(out_path, 'wb') as o:
                copy_with_progress(s, o, c.size, enc_path)

        # generate a blank save
        if cia.tmd.save_size:
            enc_path = title_root_cmd + '/data/00000001.sav'
            out_path = join(title_root, 'data', '00000001.sav')
            cipher = crypto.create_ctr_cipher(Keyslot.SD, crypto.sd_path_to_iv(enc_path))
            # in a new save, the first 0x20 are all 00s. the rest can be random
            data = cipher.encrypt(b'\0' * 0x20)
            print(f'Generating blank save at {enc_path}...')
            with open(out_path, 'wb') as o:
                o.write(data)
                o.write(b'\0' * (cia.tmd.save_size - 0x20))

        # generate and write cmd
        enc_path = content_root_cmd + '/cmd/' + cmd_filename
        out_path = join(content_root, 'cmd', cmd_filename)
        print(f'Generating {enc_path}')
        highest_index = 0
        content_ids = {}

        for record in cia.content_info:
            highest_index = record.cindex
            with cia.open_raw_section(record.cindex) as s:
                s.seek(0x100)
                cmac_data = s.read(0x100)

            id_bytes = bytes.fromhex(record.id)[::-1]
            cmac_data += record.cindex.to_bytes(4, 'little') + id_bytes

            c = crypto.create_cmac_object(Keyslot.CMACSDNAND)
            c.update(sha256(cmac_data).digest())
            content_ids[record.cindex] = (id_bytes, c.digest())

        # add content IDs up to the last one
        ids_by_index = [CMD_MISSING] * (highest_index + 1)
        installed_ids = []
        cmacs = []
        for x in range(len(ids_by_index)):
            try:
                info = content_ids[x]
            except KeyError:
                cmacs.append(bytes.fromhex('4D495353494E4720434F4E54454E5421'))
            else:
                ids_by_index[x] = info[0]
                cmacs.append(info[1])
                installed_ids.append(info[0])
        installed_ids.sort(key=lambda x: int.from_bytes(x, 'little'))

        final = (cmd_id.to_bytes(4, 'little')
                 + len(ids_by_index).to_bytes(4, 'little')
                 + len(installed_ids).to_bytes(4, 'little')
                 + (1).to_bytes(4, 'little'))
        c = crypto.create_cmac_object(Keyslot.CMACSDNAND)
        c.update(final)
        final += c.digest()

        final += b''.join(ids_by_index)
        final += b''.join(installed_ids)
        final += b''.join(cmacs)

        cipher = crypto.create_ctr_cipher(Keyslot.SD, crypto.sd_path_to_iv(enc_path))
        print(f'Writing {enc_path}')
        with open(out_path, 'wb') as o:
            o.write(cipher.encrypt(final))

    # this starts building the title info entry
    title_info_entry_data = [
        # title size
        title_size.to_bytes(8, 'little'),
        # title type, seems to usually be 0x40
        0x40.to_bytes(4, 'little'),
        # title version
        int(cia.tmd.title_version).to_bytes(2, 'little'),
        # ncch version
        cia.contents[0].version.to_bytes(2, 'little'),
        # flags_0, only checking if there is a manual
        (1 if has_manual else 0).to_bytes(4, 'little'),
        # tmd content id, always starting with 0
        (0).to_bytes(4, 'little'),
        # cmd content id
        cmd_id.to_bytes(4, 'little'),
        # flags_1, only checking save data
        (1 if cia.tmd.save_size else 0).to_bytes(4, 'little'),
        # extdataid low
        extdata_id[0:4],
        # reserved
        b'\0' * 4,
        # flags_2, only using a common value
        0x100000000.to_bytes(8, 'little'),
        # product code
        cia.contents[0].product_code.encode('ascii').ljust(0x10, b'\0'),
        # reserved
        b'\0' * 0x10,
        # unknown
        randint(0, 0xFFFFFFFF).to_bytes(4, 'little'),
        # reserved
        b'\0' * 0x2c
    ]

    print(title_info_entry_data)

    title_info_entries[cia.tmd.title_id] = b''.join(title_info_entry_data)

    with cia.open_raw_section(CIASection.Ticket) as t:
        ticket_data = t.read()

    finalize_entry_data = [
        # title id
        bytes.fromhex(cia.tmd.title_id)[::-1],
        # common key index
        ticket_data[0x1F1:0x1F2],
        # has seed
        cia.contents[0].flags.uses_seed.to_bytes(1, 'little'),
        # magic
        b'TITLE\0',
        # encrypted titlekey
        ticket_data[0x1BF:0x1CF],
        # seed, if needed
        cia.contents[0].seed if cia.contents[0].flags.uses_seed else (b'\0' * 0x10)
    ]

    finalize_entries.append(b''.join(finalize_entry_data))

with open(join(args.sd, 'cifinish.bin'), 'wb') as o:
    # magic, version, title count
    o.write(b'CIFINISH' + (1).to_bytes(4, 'little') + len(finalize_entries).to_bytes(4, 'little'))

    # add each entry to cifinish.bin
    for entry in finalize_entries:
        o.write(entry)

with TemporaryDirectory(suffix='-custom-install') as tempdir:
    # set up the common arguments for the two times we call save3ds_fuse
    save3ds_fuse_common_args = [
        join(script_dir, 'bin', platform, 'save3ds_fuse'),
        '-b', crypto.b9_path,
        '-m', args.movable,
        '--sd', args.sd,
        '--db', 'sdtitle',
        tempdir
    ]

    # extract the title database to add our own entry to
    print('Extracting Title Database...')
    subprocess.run(save3ds_fuse_common_args + ['-x'])

    for title_id, entry in title_info_entries.items():
        # write the title info entry to the temp directory
        with open(join(tempdir, title_id), 'wb') as o:
            o.write(entry)

    # import the directory, now including our title
    print('Importing into Title Database...')
    subprocess.run(save3ds_fuse_common_args + ['-i'])

print('\nFINAL STEP:\nRun custom-install-finalize through homebrew launcher.')
print('This will install a ticket and seed if required.')
