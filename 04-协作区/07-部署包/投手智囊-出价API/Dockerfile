FROM python:3.12-slim

WORKDIR /app
COPY bid_simulator.py bid_api.py ./
COPY outputs/03-基准表-曝光端-合成.csv ./outputs/03-基准表-曝光端-合成.csv

ENV PYTHONDONTWRITEBYTECODE=1
ENV PYTHONUNBUFFERED=1

CMD ["sh", "-c", "python3 bid_api.py --host 0.0.0.0 --port ${PORT:-10000}"]
