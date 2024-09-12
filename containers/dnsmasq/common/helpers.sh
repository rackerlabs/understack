#!/bin/sh

render_j2_file() {
    # use Python's jinja2 library to transform stdin to stdout replacing variables
    python3 -c 'import os; import sys; import jinja2; sys.stdout.write(jinja2.Template(sys.stdin.read()).render(env=os.environ))' \
    < "$1" > "$2"

}
