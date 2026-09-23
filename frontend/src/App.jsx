import { Navigate, Route, BrowserRouter as Router, Routes, useLocation } from 'react-router-dom'
import Layout from './components/Layout'
import AgentDetail from './pages/AgentDetail'
import AgentForm from './pages/AgentForm'
import Agents from './pages/Agents'
import CallDetail from './pages/CallDetail'
import CallLive from './pages/CallLive'
import Calls from './pages/Calls'
import Dashboard from './pages/Dashboard'
import Login from './pages/Login'
import Settings from './pages/Settings'
import { getToken } from './api/client'

function RequireAuth({ children }) {
  const location = useLocation()
  if (!getToken()) {
    return <Navigate to="/login" state={{ from: location }} replace />
  }
  return children
}

function Shell({ children }) {
  return <Layout>{children}</Layout>
}

export default function App() {
  return (
    <Router>
      <Routes>
        <Route path="/login" element={<Login />} />
        <Route
          path="/dashboard"
          element={
            <RequireAuth>
              <Shell>
                <Dashboard />
              </Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/agents"
          element={
            <RequireAuth>
              <Shell>
                <Agents />
              </Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/agents/new"
          element={
            <RequireAuth>
              <Shell>
                <AgentForm />
              </Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/agents/:id"
          element={
            <RequireAuth>
              <Shell>
                <AgentDetail />
              </Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/calls"
          element={
            <RequireAuth>
              <Shell>
                <Calls />
              </Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/calls/live/:agentId"
          element={
            <RequireAuth>
              <CallLive />
            </RequireAuth>
          }
        />
        <Route
          path="/calls/:id"
          element={
            <RequireAuth>
              <Shell>
                <CallDetail />
              </Shell>
            </RequireAuth>
          }
        />
        <Route
          path="/settings"
          element={
            <RequireAuth>
              <Shell>
                <Settings />
              </Shell>
            </RequireAuth>
          }
        />
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Router>
  )
}
