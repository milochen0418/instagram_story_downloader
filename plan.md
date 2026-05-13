## Phase 1: Core UI and State Structure ✅
- [x] Build the main single-page layout with URL input field, submit button, and status indicators
- [x] Create state management for URL input, loading states, status messages, and error handling
- [x] Design the results section with media listing cards (image/video differentiation)
- [x] Add download buttons with quality/resolution selection for video items
- [x] Style with clean, modern design — white background, indigo-600 accent, bordered cards, clean typography

## Phase 2: Instagram Story Fetching Logic ✅
- [x] Implement backend logic using instaloader to fetch story media from a given URL
- [x] Parse story URL to extract media ID and username
- [x] Retrieve media metadata (type, dimensions, available qualities)
- [x] Handle authentication via session file (instaloader login session)
- [x] Implement error handling for invalid URLs, expired stories, and auth failures

## Phase 3: Download Mechanism and Polish ✅
- [x] Implement server-side media download and serve files to client
- [x] Add quality selection dropdown for video items with highest quality pre-selected
- [x] Implement select/deselect functionality for multiple media items
- [x] Add download progress feedback and completion status
- [x] Final UI polish with loading animations, transitions, and responsive design
