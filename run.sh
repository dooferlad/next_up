#!/bin/bash

set -ex

SCRIPT=`realpath $0`
SCRIPTPATH=`dirname $SCRIPT`
cd $SCRIPTPATH
./next_up.py &
/usr/local/go/bin/go run web_server.go &
