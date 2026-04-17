FROM node:20-slim

ENV DEBIAN_FRONTEND=noninteractive

# Install Playwright system dependencies
RUN apt-get update && apt-get install -y \
    curl python3 make g++ \
    libnss3 libnspr4 libatk1.0-0 libatk-bridge2.0-0 \
    libcups2 libdrm2 libxkbcommon0 libxcomposite1 \
    libxdamage1 libxfixes3 libxrandr2 libgbm1 libpango-1.0-0 \
    libcairo2 libasound2 libatspi2.0-0 libwayland-client0 \
    fonts-noto-cjk fonts-noto-color-emoji \
    && rm -rf /var/lib/apt/lists/*

# Setup test environment
WORKDIR /test
COPY package.json ./
RUN npm install
RUN npx playwright install chromium

COPY tests/ ./tests/
COPY run_tests.sh /run_tests.sh
RUN chmod +x /run_tests.sh

WORKDIR /app
ENTRYPOINT ["/run_tests.sh"]
