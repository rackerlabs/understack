# nautobot container builds

``` bash
docker compose -f docker-compose.nautobot.yml -f docker-compose.postgres.yml -f docker-compose.redis.yml build
docker compose -f docker-compose.nautobot.yml -f docker-compose.postgres.yml -f docker-compose.redis.yml up
```
