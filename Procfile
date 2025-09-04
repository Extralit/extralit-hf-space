elastic: /usr/share/elasticsearch/bin/elasticsearch
redis: /usr/bin/redis-server
worker_high: sleep 30; rq worker-pool --num-workers 2 high
worker_default: sleep 30; rq worker-pool --num-workers 1 default
worker_ocr: sleep 30; rq worker-pool --num-workers 1 ocr
extralit: sleep 30; /bin/bash start_extralit_server.sh
