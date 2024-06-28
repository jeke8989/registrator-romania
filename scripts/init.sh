#!/bin/bash

# Install git
sudo apt install git -y

# Clone repo 
REPO_PATH=$HOME/registrator-romania
git clone https://github.com/devtolmachev/registrator-romania.git $REPO_PATH

# Work with repository
cd $REPO_PATH
git checkout develop
git pull origin

unit_service="/etc/systemd/system/registrator.service"
if [ -f $unit_service ]; then
  exit 0
fi

sudo touch $unit_service
echo """
[Unit]
Description=Registrator Service

[Service]
WorkingDirectory=$REPO_PATH
ExecStart=docker compose -f registrator-romania/docker-compose.yml up

[Install]
WantedBy=multi-user.target
""" | sudo tee $unit_service

sudo systemctl daemon-reload

echo """
to start in background, run this command
sudo systemctl start registrator.service

to run not in background use:
docker compose -f $REPO_PATH/docker-compose.yml up
"""