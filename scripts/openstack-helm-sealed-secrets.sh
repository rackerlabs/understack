#!/bin/bash -x

# function to process each YAML file
process_yaml() {
    kind=$(echo "$1" | yq e '.kind')
    if [[ "${kind}" == "Secret" ]]; then
        # its a match, encrypt it
        echo "$1" | \
            kubeseal \
            --scope cluster-wide \
            --allow-empty-data \
            -o yaml
    else
        # not a match just output it
        echo "---"
        echo "$1"
    fi
}

NL=$'\n'

# read the stream from stdin and break up each YAML doc
yaml_acc=""
while IFS= read -r line; do
    if [[ $line =~ ^---$ ]]; then
        # process each YAML file
        if [[ -n $yaml_acc ]]; then
            process_yaml "$yaml_acc"
            yaml_acc=""
        fi
    else
        # accumulate the lines of the current YAML doc
        yaml_acc+="${line}${NL}"

    fi
done

# process the last one
[[ -n $yaml_acc ]] && process_yaml "$yaml_acc"
exit 0
