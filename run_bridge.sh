#!/bin/bash

#pg_isready -h postgres -p 5432
nc -zv postgres 5432

if [ $? -eq 0 ]; then
  echo "Postgres is found"
else
  echo "Postgres is not found"
  exit -1
fi

nc -zv rabbitmq 5672

if [ $? -eq 0 ]; then
  echo "RabbitMQ is found"
else
  echo "RabbitMQ is not found"
  exit -1
fi


python3 bridge/manage.py migrate
python3 bridge/manage.py createuser --username admin --password admin --staff --superuser
python3 bridge/manage.py createuser --username manager --password manager --role 2
python3 bridge/manage.py createuser --username service --password service --role 4
python3 bridge/manage.py populate --all

python3 bridge/manage.py runserver 0.0.0.0:8998
