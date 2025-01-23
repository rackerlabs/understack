
cd python/diff-nautobot-understack
python3 -m venv .venv
source .venv/bin/activate
poetry lock
poetry install

export NB_TOKEN=<get_token_from_nautobot_dev>
poetry run diff-network
