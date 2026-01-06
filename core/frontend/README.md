# AI TaskManagement OS - Frontend

Next.js frontend application for the AI TaskManagement OS.

## Features

- **Dashboard**: Real-time LBS metrics with KPI cards and task list
- **Hub Chat**: Interactive chat with the central PM agent
- **Inbox**: Review and process messages from Spoke agents
- **Spokes**: Manage and chat with project-specific agents
- **Dark Theme**: Beautiful, modern UI optimized for productivity

## Quick Start

### 1. Ensure Backend is Running

The frontend requires the backend API at http://localhost:8000

```bash
# In app/backend
python main.py
```

### 2. Start Frontend Dev Server

```bash
cd app/frontend
npm run dev
```

Open **http://localhost:3000** in your browser.

## Pages

| Route | Description |
|-------|-------------|
| `/` | Home page with navigation cards |
| `/dashboard` | LBS Dashboard with metrics |
| `/hub` | Chat with Hub (PM) agent |
| `/inbox` | Process Spoke messages |
| `/spokes` | List all projects |
| `/spokes/[name]` | Chat with specific Spoke |

## API Integration

The frontend proxies API requests to the backend:
- Frontend: `http://localhost:3000/api/*`
- Backend: `http://localhost:8000/api/*`

Configured in `next.config.ts`.

## Tech Stack

- **Next.js 16** - React framework with App Router
- **TypeScript** - Type-safe development
- **Tailwind CSS** - Utility-first styling
- **Dark Theme** - Built-in dark mode

## Development

```bash
# Install dependencies
npm install

# Run dev server (hot reload)
npm run dev

# Build for production
npm run build

# Start production server
npm start
```

## Design Philosophy

Following the web_application_development guidelines:
- ✅ **Rich Aesthetics**: Gradient text, glassmorphism borders, smooth transitions
- ✅ **Dark Mode**: Premium dark theme throughout
- ✅ **Micro-animations**: Hover effects and loading states
- ✅ **Responsive**: Works on all screen sizes
- ✅ **No Placeholders**: All UI is functional

## Troubleshooting

### "Failed to load dashboard data"
- Ensure backend is running at http://localhost:8000
- Check backend console for errors

### API requests failing
- Verify `next.config.ts` proxy configuration
- Check that backend CORS allows `localhost:3000`

### Build errors
- Delete `.next` folder and rebuild: `rm -rf .next && npm run build`
- Ensure all dependencies installed: `npm install`

---

**Built with:** Next.js 16 • TypeScript • Tailwind CSS
