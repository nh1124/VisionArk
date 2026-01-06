# Frontend Dockerfile
FROM node:20-alpine

WORKDIR /app

# Build argument for API URL (needed at build time for Next.js rewrites)
ARG NEXT_PUBLIC_API_URL=http://localhost:8000
ENV NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL}

# Install dependencies
COPY package*.json ./
RUN npm ci

# Copy application code
COPY . .

# Build the application
RUN npm run build

# Expose port
EXPOSE 3000

# Run the application
CMD ["npm", "start"]
