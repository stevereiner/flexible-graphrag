FROM node:24-alpine

WORKDIR /app

# Copy package files
COPY package*.json ./

# Install dependencies
RUN npm ci

# Copy source code
COPY . .

# Replace proxy config with Docker-specific version
RUN mv proxy.docker.conf.json proxy.conf.json

# Expose port
EXPOSE 4200

# Start the development server with proxy (no base href modification)
CMD ["npm", "run", "start", "--", "--host", "0.0.0.0", "--port", "4200"]
