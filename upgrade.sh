#!/bin/sh

exec ansible-playbook -i bootstrap/inventory.yml bootstrap/upgrade.yml --skip-tags harden "$@"
