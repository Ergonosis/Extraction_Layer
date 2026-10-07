import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthGuard } from './components/AuthGuard'
import { AuthProvider } from './context/AuthContext'
import { ConnectionsPage } from './pages/ConnectionsPage'
import { LoginPage } from './pages/LoginPage'

function App() {
  return (
    <AuthProvider>
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            path="/connections"
            element={
              <AuthGuard>
                <ConnectionsPage />
              </AuthGuard>
            }
          />
          <Route path="/" element={<Navigate to="/connections" replace />} />
          <Route path="*" element={<Navigate to="/connections" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
