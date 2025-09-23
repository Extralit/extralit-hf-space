elastic: /usr/share/elasticsearch/bin/elasticsearch
redis: /usr/bin/redis-server
worker_high: sleep 30; python -m extralit_server worker --num-workers 2 --queues high
worker_default: sleep 30; python -m extralit_server worker --num-workers 2 --queues default --queues ocr
extralit: sleep 30; /bin/bash start_extralit_server.sh
