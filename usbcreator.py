#!/usr/bin/env python

import argparse
import inspect
import os
import pipes
import platform
import subprocess
import sys

# See http://stackoverflow.com/a/847800/343845 and http://bugs.python.org/issue9723
from pipes import quote

if sys.version_info < (2,7):
    print >> sys.stderr, "must be run with at least Python 2.7"
    sys.exit(1)

if platform.system() != "Darwin":
    sys.exit("this script only works on OS X")

# Get command line arguments...
parser = argparse.ArgumentParser(description="Burn disk images to flash drives\n\nNote that this tool requires root access!", formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("image", help="path to the image to burn - if an ISO is specified, it will be converted to IMG format first if an IMG does not exist")
parser.add_argument("-s", "--silent", action="store_true", help="do not ask for confirmation when writing the image file to the specified disk")
parser.add_argument("-v", "--verbose", action="store_true", help="display more detailed output")
parser.add_argument("-d", "--disk", metavar="id", type=int, default=-1, help="the disk ID of the disk to burn the image file to (i.e. to burn to /dev/disk1, specify 1); omit this argument to be shown a list of disks and choose the target disk during execution")
args = parser.parse_args()

# Check for root - we do this down here so the user can still see help info
# or argument errors without needing root permissions
if not os.geteuid() == 0:
    scriptName = os.path.basename(os.path.realpath(inspect.getfile(inspect.currentframe())))
    sys.exit("%s: must be root to run this program" % scriptName)

# Keep track of whether the user *initially* selected a target disk
wasDiskSpecified = args.disk >= 0

# Print all commands run in subprocesses when using verbose output
printSubprocessCommands = args.verbose

# Runs an arbitrary command in a subprocess and
# exits gracefully after printing status code
# and error info if it does not complete successfully
def runEssentialCommand(cmd):
    if not cmd:
        raise Exception("Empty command string passed to runEssentialCommand")

    if printSubprocessCommands:
        print cmd

    # The first token in the command string is the name of the command we want to run
    commandName = cmd.split()[0]

    try:
        retcode = subprocess.call(cmd, shell=True)
        if retcode != 0:
            if retcode < 0:
                print >> sys.stderr, "%s was terminated by signal" % commandName, -retcode
            elif retcode > 0:
                print >> sys.stderr, "%s returned" % commandName, retcode
            sys.exit(1)
    except KeyboardInterrupt:
        sys.exit('\n')
    except OSError, e:
        print >> sys.stderr, "Execution failed:", e
        sys.exit(1)

# Converts an ISO file to an image formatted as UDRW
def convertDiskToUDRW(isoImage, imgImage):
    runEssentialCommand('hdiutil convert -format UDRW -o %s %s' % (quote(imgImage), quote(isoImage)))

# Print disk information
def printDiskInformation(diskId = -1):
    if diskId >= 0:
        runEssentialCommand("diskutil list /dev/disk%d" % diskId)
    else:
        runEssentialCommand("diskutil list")

# Unmount all partitions on the target disk
def unmountPartitions(diskId):
    runEssentialCommand("diskutil unmountDisk /dev/disk%d" % diskId)

# Write the image file to the USB drive
def writeImageFile(diskId, imageFile):
    runEssentialCommand('sudo dd if=%s of=/dev/rdisk%d bs=1m' % (quote(imageFile), diskId))

# Ejects the given disk
def ejectDisk(diskId):
    runEssentialCommand("diskutil eject /dev/disk%d" % diskId)

# Find the base path of the image file (we don't actually use the user-supplied
# extension to determine the action to take)
imageRoot, imageExt = os.path.splitext(os.path.realpath(args.image))

# TODO: we should probably verify whether the IMG file actually is in UDRW format...
if imageExt.lower() != ".img" and imageExt.lower() != ".iso":
    sys.exit("Image file must be a .img or .iso")

# Paths to image files in both formats
imgImage = imageRoot + ".img"
isoImage = imageRoot + ".iso"

# If the burn file (IMG) doesn't exist, we must create it...
if not os.path.exists(imgImage):
    if (args.verbose):
        print "Unable to find IMG file; looking for ISO file..."

    # Do we have an ISO to use to generate the IMG? If not we can't do anything
    if not os.path.exists(isoImage):
        if (args.verbose):
            print "Unable to find IMG or so ISO files at the following paths:"
            print "\t" + imgImage
            print "\t" + isoImage
        sys.exit(1)

    # We found an ISO image, generate the IMG from it...
    print "Found ISO file; converting to IMG..."
    convertDiskToUDRW(isoImage, imgImage)

# OS X likes to name things other than what we tell them to...
if not os.path.exists(imgImage) and os.path.exists(imgImage + ".dmg"):
    try:
        os.rename(imgImage + ".dmg", imgImage)
    except OSError, e:
        print >> sys.stderr, "Execution failed:", e
        sys.exit(1)

# Display the disks on the system to avoid the user having to
# issue a separate command in order to choose the right one
if not wasDiskSpecified:
    printDiskInformation()

    # Get the target disk from the user
    while args.disk < 0:
        try:
            args.disk = int(raw_input("Choose a disk to write to: /dev/disk"))
        except ValueError:
            args.disk = -1
        except KeyboardInterrupt:
            sys.exit('\n') # properly push down the terminal prompt
else:
    if not args.silent:
        # Display the details of the target disk
        print "Confirm target disk details:"
        printDiskInformation(args.disk)

if not args.silent:
    # Confirm that the user really wants to write to the disk (what if they accidentally entered their main HD?)
    confirmWrite = raw_input("Erase /dev/disk%d and write %s (y/n)? " % (args.disk, os.path.basename(imgImage))).lower()
    if confirmWrite != 'y' and confirmWrite != 'yes':
        sys.exit("Cancelled - /dev/disk%d was not altered" % args.disk)

# Unmount partitions on the target disk
unmountPartitions(args.disk)

print "Writing image file (this may take a little while)..."

# write the image file, then eject it
writeImageFile(args.disk, imgImage)
ejectDisk(args.disk)
