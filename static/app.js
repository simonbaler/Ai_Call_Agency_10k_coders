/**
 * 10,000 Coders AI Voice Calling & Demo Booking Console
 * Real-time Telemetry, Live Dialogue Stream, Stepper Progress & Cockpit Controller
 */

// DOM References
const callForm = document.getElementById('callForm')
const callBtn = document.getElementById('callBtn')
const statusText = document.getElementById('status')
const connectingLoader = document.getElementById('connecting')
const statusLight = document.querySelector('.status-light')

// Live Call Cockpit Elements
const liveCallCard = document.getElementById('liveCallCard')
const liveCallStatusBadge = document.getElementById('liveCallStatusBadge')
const liveCallStateLabel = document.getElementById('liveCallStateLabel')
const liveStudentName = document.getElementById('liveStudentName')
const liveStudentDetails = document.getElementById('liveStudentDetails')
const audioVisualizer = document.getElementById('audioVisualizer')
const liveCallTimer = document.getElementById('liveCallTimer')
const liveProgressFill = document.getElementById('liveProgressFill')
const liveBadgeTrack = document.getElementById('liveBadgeTrack')
const liveBadgeSlot = document.getElementById('liveBadgeSlot')
const liveBadgeStatus = document.getElementById('liveBadgeStatus')
const liveBadgeLang = document.getElementById('liveBadgeLang')
const liveDialogueStream = document.getElementById('liveDialogueStream')
const dialogueCount = document.getElementById('dialogueCount')

// Stepper Nodes
const stepNode1 = document.getElementById('stepNode1')
const stepNode2 = document.getElementById('stepNode2')
const stepNode3 = document.getElementById('stepNode3')
const stepNode4 = document.getElementById('stepNode4')
const stepNode5 = document.getElementById('stepNode5')

// KPI Stats Elements
const statTotalCalls = document.getElementById('statTotalCalls')
const statBookedDemos = document.getElementById('statBookedDemos')
const statPythonLeads = document.getElementById('statPythonLeads')
const statJavaLeads = document.getElementById('statJavaLeads')

// Batch & Logs Elements
const customerFile = document.getElementById('customerFile')
const automationToggle = document.getElementById('automationToggle')
const agentState = document.getElementById('agentState')
const logRows = document.getElementById('logRows')
const logSummary = document.getElementById('logSummary')
const refreshLogsBtn = document.getElementById('refreshLogs')

// Booked Courses Elements
const coursesToggle = document.getElementById('coursesToggle')
const coursesPanel = document.getElementById('coursesPanel')
const courseCards = document.getElementById('courseCards')
const bookingCount = document.getElementById('bookingCount')
const pythonCount = document.getElementById('pythonCount')
const javaCount = document.getElementById('javaCount')

// Copilot Elements
const chatForm = document.getElementById('chatForm')
const chatInput = document.getElementById('chatInput')
const chatMessages = document.getElementById('chatMessages')
const sidebarToggle = document.getElementById('sidebarToggle')

// State Cache
let selectedCourses = []
let activeFilter = 'all'
let lastTranscriptHash = ''
let isCallActive = false
let pollInterval = 1400
let pollTimerId = null

/**
 * Format seconds to MM:SS string
 */
function formatDuration(seconds) {
  const s = Math.max(0, parseInt(seconds || 0, 10))
  const m = Math.floor(s / 60)
  const rem = s % 60
  return `${m.toString().padStart(2, '0')}:${rem.toString().padStart(2, '0')}`
}

/**
 * Update the 5-step progress stepper nodes visually
 */
function updateStepper(pct) {
  liveProgressFill.style.width = `${Math.min(100, Math.max(0, pct))}%`

  const nodes = [
    { node: stepNode1, min: 10, complete: 25 },
    { node: stepNode2, min: 25, complete: 50 },
    { node: stepNode3, min: 50, complete: 75 },
    { node: stepNode4, min: 75, complete: 95 },
    { node: stepNode5, min: 95, complete: 100 }
  ]

  nodes.forEach(({ node, min, complete }) => {
    if (!node) return
    node.classList.remove('active', 'completed')
    if (pct >= complete) {
      node.classList.add('completed')
    } else if (pct >= min) {
      node.classList.add('active')
    }
  })
}

/**
 * Render dialogue stream messages without re-rendering if unchanged
 */
function renderDialogue(transcript) {
  if (!transcript || !transcript.length) {
    liveDialogueStream.innerHTML = `
      <div class="dialogue-empty">
        <span>🎙️</span>
        <p>Audio channel is standing by. When candidate speaks, live speech transcription will appear here in real time.</p>
      </div>`
    dialogueCount.textContent = '0 utterances'
    lastTranscriptHash = ''
    return
  }

  const hash = JSON.stringify(transcript)
  if (hash === lastTranscriptHash) return
  lastTranscriptHash = hash

  dialogueCount.textContent = `${transcript.length} turns recorded`

  liveDialogueStream.innerHTML = transcript.map(entry => {
    const role = (entry.role || '').toLowerCase()
    const time = entry.time || ''
    const text = (entry.text || '').trim()

    if (role === 'officer' || role === 'agent') {
      return `
        <div class="dialogue-bubble officer-bubble">
          <div class="bubble-meta">
            <span class="sender">✦ Admissions Officer (Ajay)</span>
            <span class="time">${time}</span>
          </div>
          <div class="bubble-text">${escapeHtml(text)}</div>
        </div>`
    } else if (role === 'student' || role === 'user') {
      return `
        <div class="dialogue-bubble student-bubble">
          <div class="bubble-meta">
            <span class="time">${time}</span>
            <span class="sender">Candidate Speech 🧑‍💻</span>
          </div>
          <div class="bubble-text">${escapeHtml(text)}</div>
        </div>`
    } else {
      return `
        <div class="dialogue-bubble system-bubble">
          <span>${escapeHtml(text)} · ${time}</span>
        </div>`
    }
  }).join('')

  liveDialogueStream.scrollTop = liveDialogueStream.scrollHeight
}

/**
 * Escape HTML to prevent injection
 */
function escapeHtml(text) {
  const div = document.createElement('div')
  div.textContent = text || ''
  return div.innerHTML
}

/**
 * Poll live call telemetry and update dashboard in real time
 */
async function pollLiveCall() {
  try {
    const res = await fetch('/api/live_call')
    if (!res.ok) return
    const data = await res.json()

    const activeCall = data.active_call || {}
    const stats = data.stats || {}

    // Update KPI Statistics
    if (statTotalCalls) statTotalCalls.textContent = stats.total_calls ?? '--'
    if (statBookedDemos) statBookedDemos.textContent = stats.booked_demos ?? '--'
    if (statPythonLeads) statPythonLeads.textContent = stats.python_leads ?? '--'
    if (statJavaLeads) statJavaLeads.textContent = stats.java_leads ?? '--'

    isCallActive = !!activeCall.active

    if (isCallActive) {
      // LIVE CALL IN PROGRESS
      liveCallStatusBadge.classList.add('active-live')
      liveCallStateLabel.textContent = `LIVE CALL · ${(activeCall.stage_title || 'CONNECTING').toUpperCase()}`

      liveStudentName.textContent = activeCall.student_name || 'Prospective Student'
      const collegeStr = activeCall.student_college ? ` · ${activeCall.student_college}` : ''
      const ageStr = activeCall.student_age ? ` · ${activeCall.student_age} yrs` : ''
      liveStudentDetails.textContent = `${activeCall.student_phone || ''}${collegeStr}${ageStr}`

      audioVisualizer.classList.add('speaking')
      liveCallTimer.textContent = formatDuration(activeCall.duration_seconds)

      updateStepper(activeCall.progress_pct || 20)

      liveBadgeTrack.textContent = activeCall.course_selected || 'Detecting...'
      liveBadgeSlot.textContent = activeCall.demo_date
        ? `${activeCall.demo_date} ${activeCall.demo_time ? 'at ' + activeCall.demo_time : ''}`
        : 'Pending selection'
      liveBadgeStatus.textContent = (activeCall.booking_status || 'In Progress').toUpperCase()
      liveBadgeLang.textContent = activeCall.language || 'en-IN'

      renderDialogue(activeCall.transcript)
    } else {
      // NO ACTIVE CALL
      audioVisualizer.classList.remove('speaking')

      if (activeCall.stage === 'confirmed' || activeCall.stage === 'completed') {
        liveCallStatusBadge.classList.remove('active-live')
        liveCallStateLabel.textContent = activeCall.stage === 'confirmed'
          ? 'DEMO BOOKING CONFIRMED'
          : 'CALL COMPLETED'

        liveStudentName.textContent = activeCall.student_name || 'Last Candidate'
        liveBadgeStatus.textContent = activeCall.stage === 'confirmed' ? 'CONFIRMED' : 'COMPLETED'
        updateStepper(100)

        if (activeCall.transcript) {
          renderDialogue(activeCall.transcript)
        }
      } else {
        liveCallStatusBadge.classList.remove('active-live')
        liveCallStateLabel.textContent = 'Standby / Monitoring'
        liveStudentName.textContent = 'No Call Currently In Progress'
        liveStudentDetails.textContent = 'Initiate an outbound call below or start queue automation to stream live speech.'
        updateStepper(0)
        liveBadgeTrack.textContent = 'Detecting...'
        liveBadgeSlot.textContent = 'Pending selection'
        liveBadgeStatus.textContent = 'Standby'
        liveBadgeLang.textContent = 'en-IN'
        renderDialogue([])
      }
    }
  } catch (err) {
    console.debug('Telemetry poll error:', err)
  } finally {
    // Schedule next poll (fast when active, slower when standby)
    const delay = isCallActive ? 1200 : 3500
    clearTimeout(pollTimerId)
    pollTimerId = setTimeout(pollLiveCall, delay)
  }
}

/**
 * Handle Single Direct Outbound Call Initiation
 */
function setConnectingUI(isConnecting) {
  if (connectingLoader) connectingLoader.style.visibility = isConnecting ? 'visible' : 'hidden'
  if (callBtn) callBtn.disabled = isConnecting
  if (statusText) statusText.textContent = isConnecting ? 'Securing Twilio audio bridge...' : 'Ready to dial student'
  if (statusLight) statusLight.classList.toggle('active', isConnecting)
}

callForm.addEventListener('submit', async (event) => {
  event.preventDefault()
  if (!callForm.reportValidity()) return

  setConnectingUI(true)
  const formData = new FormData(callForm)

  const payload = {
    name: formData.get('name').trim(),
    age: formData.get('age') ? formData.get('age').trim() : '',
    college: formData.get('college') ? formData.get('college').trim() : '',
    phone: formData.get('phone').trim(),
    language: formData.get('language') || 'en-IN'
  }

  try {
    const controller = new AbortController()
    const timeoutId = setTimeout(() => controller.abort(), 20000)
    const resp = await fetch('/trigger_call', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
      signal: controller.signal
    })
    clearTimeout(timeoutId)
    const data = await resp.json().catch(() => ({}))

    if (resp.ok) {
      statusText.textContent = data.status === 'simulated'
        ? 'Simulation connected · Speech live'
        : `Calling ${payload.name}... (${data.call_sid || 'Initiated'})`

      // Immediately trigger fast polling so the Live Cockpit opens instantly
      clearTimeout(pollTimerId)
      pollLiveCall()
      refreshLogs()
      refreshBookings()
    } else {
      statusText.textContent = data.error || 'Failed to start call'
    }
  } catch (err) {
    statusText.textContent = err.name === 'AbortError'
      ? 'The call request timed out. Check Flask, ngrok, and Twilio status.'
      : err.message || 'Connection error'
  } finally {
    setTimeout(() => setConnectingUI(false), 1800)
  }
})

/**
 * Render Call Telemetry Table
 */
function renderLogs(logs) {
  if (logSummary) logSummary.textContent = `${logs.length} records`
  if (!logRows) return

  if (!logs.length) {
    logRows.innerHTML = '<tr><td colspan="6" class="empty-state">No call activity recorded yet. First call will log here.</td></tr>'
    return
  }

  logRows.innerHTML = logs.map(log => {
    const name = log.name || 'Candidate'
    const college = log.college || 'College not listed'
    const phone = log.phone || '--'
    const lang = log.language || 'en-IN'
    const status = (log.status || log.event || 'initiated').toLowerCase()
    const duration = log.duration ? `${log.duration}s` : '0s'
    const time = log.timestamp || '--'

    return `
      <tr>
        <td>
          <div class="user-cell">
            <strong>${escapeHtml(name)}</strong>
            <small>${escapeHtml(college)}</small>
          </div>
        </td>
        <td><code>${escapeHtml(phone)}</code></td>
        <td><span class="lang-tag">${escapeHtml(lang)}</span></td>
        <td><span class="status-tag status-${status}">${escapeHtml(status)}</span></td>
        <td>${duration}</td>
        <td><small>${escapeHtml(time)}</small></td>
      </tr>`
  }).join('')
}

async function refreshLogs() {
  try {
    const res = await fetch('/call_logs')
    if (!res.ok) return
    const data = await res.json()
    renderLogs(data.logs || [])

    if (data.agent && agentState) {
      agentState.textContent = data.agent.running
        ? `Calling queue · ${data.agent.queued} remaining`
        : `${data.agent.completed || 0} completed · ready to assist`
    }
  } catch (err) {
    console.debug('Failed to refresh logs:', err)
  }
}

if (refreshLogsBtn) {
  refreshLogsBtn.addEventListener('click', refreshLogs)
}

/**
 * Lead CSV Upload & Batch Automation
 */
if (customerFile) {
  customerFile.addEventListener('change', async () => {
    if (!customerFile.files[0]) return
    const body = new FormData()
    body.append('file', customerFile.files[0])

    if (agentState) agentState.textContent = 'Importing leads CSV...'
    try {
      const resp = await fetch('/upload_customers', { method: 'POST', body })
      const data = await resp.json()
      if (resp.ok) {
        if (agentState) agentState.textContent = `${data.imported} leads queued for outreach`
      } else {
        if (agentState) agentState.textContent = data.error || 'Import failed'
      }
    } catch (err) {
      if (agentState) agentState.textContent = 'Upload network error'
    } finally {
      customerFile.value = ''
      refreshLogs()
    }
  })
}

if (automationToggle) {
  automationToggle.addEventListener('change', async () => {
    if (!automationToggle.checked) {
      if (agentState) agentState.textContent = 'Automation paused'
      await fetch('/automation', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ enabled: false })
      })
      return
    }

    if (agentState) agentState.textContent = 'Starting autonomous queue...'
    try {
      const resp = await fetch('/automation', { method: 'POST' })
      const data = await resp.json()
      if (resp.ok && data.started) {
        if (agentState) agentState.textContent = 'Agent is calling leads sequentially'
      } else {
        if (agentState) agentState.textContent = data.agent?.queued ? 'Queue active' : 'Import a CSV first'
      }
    } catch (err) {
      if (agentState) agentState.textContent = 'Failed to activate queue'
    }
    refreshLogs()
  })
}

/**
 * Booked Demo Sessions Management
 */
function renderCourses(filter) {
  activeFilter = filter
  const list = filter === 'all'
    ? selectedCourses
    : selectedCourses.filter(c => (c.course_name || '').toLowerCase().includes(filter))

  if (bookingCount) bookingCount.textContent = selectedCourses.length
  if (pythonCount) pythonCount.textContent = selectedCourses.filter(c => (c.course_name || '').toLowerCase().includes('python')).length
  if (javaCount) javaCount.textContent = selectedCourses.filter(c => (c.course_name || '').toLowerCase().includes('java')).length

  if (!courseCards) return

  if (!list.length) {
    courseCards.innerHTML = '<p class="empty-state">No booked demo sessions found for this selection.</p>'
    return
  }

  courseCards.innerHTML = list.map(course => {
    const isPython = (course.course_name || '').toLowerCase().includes('python')
    const icon = isPython ? '🐍' : '☕'
    const name = course.student_name || 'Candidate'
    const college = course.college || 'College not recorded'
    const courseName = course.course_name || 'Full Stack Bootcamp'
    const day = course.demo_date || 'TBD'
    const time = course.demo_time || '10:00 AM'
    const phone = course.phone_number || course.phone || ''

    return `
      <article class="booking-card-item">
        <div class="card-top">
          <div class="card-title">
            <strong>${icon} ${escapeHtml(courseName)}</strong>
            <small>${escapeHtml(name)} · ${escapeHtml(college)}</small>
          </div>
          <span class="confirmed-tag ${course.admin_status === 'accepted' ? 'accepted-tag' : ''}">${course.admin_status === 'accepted' ? 'ACCEPTED' : 'PENDING REVIEW'}</span>
        </div>
        <div class="card-meta-row">
          <span>📅 ${escapeHtml(day)} at ${escapeHtml(time)}</span>
          <span class="card-phone">${escapeHtml(phone)}</span>
        </div>
        <div class="card-action-row">
          <span class="notification-state">${course.notification_status === 'sent' ? 'Confirmation sent' : course.notification_status === 'failed' ? 'Notification failed' : 'Awaiting admin approval'}</span>
          ${course.admin_status === 'accepted' ? '' : `<button class="accept-booking-btn" data-booking-id="${escapeHtml(course.booking_id || '')}" type="button">Accept & Notify</button>`}
        </div>
      </article>`
  }).join('')

  courseCards.querySelectorAll('.accept-booking-btn').forEach(button => {
    button.addEventListener('click', async () => {
      button.disabled = true
      button.textContent = 'Sending...'
      try {
        const response = await fetch(`/bookings/${encodeURIComponent(button.dataset.bookingId)}/accept`, { method: 'POST' })
        const data = await response.json()
        if (!response.ok) throw new Error(data.error || 'Notification failed')
        await refreshBookings()
      } catch (error) {
        button.disabled = false
        button.textContent = 'Retry notification'
        window.alert(error.message)
      }
    })
  })
}

async function refreshBookings() {
  try {
    const res = await fetch('/selected_courses')
    if (!res.ok) return
    const data = await res.json()
    selectedCourses = data.courses || []
    renderCourses(activeFilter)
  } catch (err) {
    console.debug('Failed to fetch courses:', err)
  }
}

if (coursesToggle) {
  coursesToggle.addEventListener('click', () => {
    const isExpanded = coursesToggle.getAttribute('aria-expanded') === 'true'
    coursesToggle.setAttribute('aria-expanded', String(!isExpanded))
    coursesPanel.hidden = isExpanded
    coursesToggle.innerHTML = isExpanded
      ? 'Show Booked Sessions <span>+</span>'
      : 'Hide Booked Sessions <span>−</span>'
    if (!isExpanded) {
      refreshBookings()
    }
  })
}

document.querySelectorAll('.filter-pill').forEach(btn => {
  btn.addEventListener('click', () => {
    document.querySelectorAll('.filter-pill').forEach(b => b.classList.remove('active'))
    btn.classList.add('active')
    renderCourses(btn.dataset.filter || 'all')
  })
})

/**
 * Counselor Copilot Chatbot
 */
function addChatMessage(text, role) {
  if (!chatMessages) return
  const bubble = document.createElement('div')
  bubble.className = `chat-bubble ${role}-bubble`

  if (role === 'agent') {
    bubble.innerHTML = `
      <span class="bubble-avatar">✦</span>
      <div class="bubble-content"><p>${escapeHtml(text)}</p></div>`
  } else {
    bubble.innerHTML = `
      <div class="bubble-content"><p>${escapeHtml(text)}</p></div>`
  }

  chatMessages.appendChild(bubble)
  chatMessages.scrollTop = chatMessages.scrollHeight
}

async function askAssistant(question) {
  if (!question || !question.trim()) return
  const query = question.trim()
  addChatMessage(query, 'user')
  if (chatInput) chatInput.value = ''

  try {
    const resp = await fetch('/assistant', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: query })
    })
    const data = await resp.json()
    addChatMessage(resp.ok ? data.answer : (data.error || 'Desk copilot is momentarily unavailable.'), 'agent')
  } catch (err) {
    addChatMessage('Could not connect to Copilot service.', 'agent')
  }
}

if (chatForm) {
  chatForm.addEventListener('submit', (e) => {
    e.preventDefault()
    if (chatInput && chatInput.value) askAssistant(chatInput.value)
  })
}

document.querySelectorAll('.suggestion-chips button').forEach(btn => {
  btn.addEventListener('click', () => {
    const q = btn.dataset.question || btn.textContent
    askAssistant(q)
  })
})

// Mobile Sidebar Toggle
if (sidebarToggle) {
  sidebarToggle.addEventListener('click', () => {
    const sidebar = document.getElementById('sidebar')
    if (sidebar) sidebar.classList.toggle('open')
  })
}

document.querySelectorAll('.nav-item').forEach(item => {
  item.addEventListener('click', () => {
    document.querySelectorAll('.nav-item').forEach(n => n.classList.remove('active'))
    item.classList.add('active')
    const sidebar = document.getElementById('sidebar')
    if (sidebar) sidebar.classList.remove('open')
  })
})

// Initial Bootstrapping
document.addEventListener('DOMContentLoaded', () => {
  pollLiveCall()
  refreshBookings()
  refreshLogs()
})

