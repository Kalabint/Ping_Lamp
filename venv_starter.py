#!/bin/bash

# Check if there's any directory in the current directory that contains bin/activate
venv_path=$(find . -maxdepth 2 -name "bin" -type d -exec find {} -maxdepth 1 -name "activate" \;)

if [ -z "$venv_path" ]; then
    # If no virtual environment exists, ask for a name and create a new one
    echo "No Python virtual environment found."
    echo -n "Enter a name for a new virtual environment: "
    read venv_name
    python3 -m venv $venv_name
    echo "Virtual environment $venv_name created."
    source "$venv_name/bin/activate"
else
    # If a virtual environment exists, activate it
    venv_dir=$(dirname $(dirname $venv_path))
    echo "Activating virtual environment in $venv_dir..."
    source "$venv_path"
fi