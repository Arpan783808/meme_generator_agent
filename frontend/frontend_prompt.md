# Prompt for AI Frontend Generator

**Goal:** Create a minimalist, futuristic "Terminal-themed" conversational UI for a Meme Generator application.

## 1. Visual Style & Theme
- **Theme:** "Cyberpunk / Space Terminal".
- **Background:** 
  - Deep space black (`#0a0b10`).
  - Subtle animated nebula/starfield in the background (using CSS or a low-opacity image).
  - The terminal window itself should be transparent or have a very low opacity dark background to let the stars shine through.
- **Typography:** Monospaced font (e.g., Courier New, Fira Code) with a "glow" effect (text-shadow) to mimic a CRT monitor.
- **Color Palette:**
  - Primary Text: Terminal Green (`#00ff41`).
  - System Logs/Secondary Text: Dimmed Green or Gray (`rgba(0, 255, 65, 0.5)`).
  - Errors: Red/Orange.
- **Layout:**
  - A single, large "window" centered on the screen (e.g., `90vw` width, `90vh` height).
  - **No visible borders or headers** initially – extremely clean.
  - **Scrollbar:** Custom "thin" scrollbar styled to match the theme (green thumb, transparent track).

## 2. Core Interaction Model
The UI behaves like a command-line interface (CLI) but with modern chat features.

### A. Initial State
- A blinking cursor at the top.
- User types a prompt (e.g., "funny cat meme") and hits ENTER.

### B. "Fixed Prompt" State
- Once submitted, the user's prompt is "fixed" at the very top of the terminal (e.g., `> funny cat meme`).
- A **Scrollable Log Container** appears below it.

### C. The Log Container (Chat History)
- This area displays the conversation and system events.
- **Auto-Scroll Behavior:**
  - It should auto-scroll to the bottom when new messages arrive *only if* the user is already near the bottom.
  - If the user scrolls up to read history, *do not* force them back down.
- **Collapsible History:**
  - Include a small toggle button (e.g., Chevron icon) to collapse/expand older logs if it gets too cluttered.
- **Content Types:**
  - `[SYS]`: Text logs from the system (e.g., "Initializing...", "Generating...").
  - `[IMG]`: Generated meme images displayed inline (max height ~60vh).

### D. Input Area
- Located at the bottom (or follows the logs).
- **Ghost Input:** Use a hidden HTML input over a visible `span` to maintain perfect alignment and blinking cursor animations.
- The input label changes based on context:
  - Default: `$`
  - Approval: `Approve (Y/N) >`
  - Feedback: `Feedback >`

## 3. Communication Architecture
The frontend must manage two communication channels: **HTTP** and **WebSocket**.

### Step 1: WebSocket Connection (CRITICAL)
- Before sending any generation request, the frontend **must** establish a WebSocket connection.
- **Endpoint:** `ws://localhost:8000/ws/{client_id}`
- **Client ID:** Generate a random unique ID on the client side.
- **Wait for Connection:** The app *must* wait for the WebSocket `onopen` event before proceeding.

### Step 2: Generation Request
- **Method:** POST
- **Endpoint:** `http://localhost:8000/generate-meme`
- **Body:** `{ "prompt": "user input", "client_id": "the_ws_client_id" }`

### Step 3: Real-time Events (WebSocket)
Handle incoming JSON messages from the WebSocket:
1.  **Event Logs:**
    - Format: `{ "type": "event_log", "message": "..." }`
    - Action: Display as a system log line.
2.  **Approval Request:**
    - Format: `{ "type": "approval_request", "meme_url": "...", "command_id": "..." }`
    - Action:
        - Display the image.
        - Switch Input Mode to **Approval Mode**.
        - Prompt user: `Approve (Y/N) >`

### Step 4: User Decisions (Human-in-the-Loop)
- **If User Types 'Y' (Yes):**
    - Send: `{ "type": "decision", "approved": "true", "command_id": "..." }` via WebSocket.
- **If User Types 'N' (No):**
    - Switch Input Mode to **Feedback Mode**.
    - Prompt user: `Feedback >`
    - User types feedback.
    - Send: `{ "type": "decision", "approved": "false", "feedback": "user feedback", "command_id": "..." }` via WebSocket.

*Note: The backend currently expects "approved" as a string ("true"/"false").*

## 4. Technology Stack
- **Framework:** React + Vite
- **Styling:** Tailwind CSS (preferred for easy layout/transparency)
- **Icons:** Lucide-React (for UI elements like chevrons)
