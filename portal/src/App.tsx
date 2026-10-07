import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthGuard } from './components/AuthGuard'
import { DevAuthBanner } from './components/DevAuthBanner'
import { AuthProvider } from './context/AuthContext'
import { AppLayout } from './layouts/AppLayout'
import { ConnectionsPage } from './pages/ConnectionsPage'
import { FileUploadPage } from './pages/FileUploadPage'
import { LoginPage } from './pages/LoginPage'

function App() {
  return (
    <AuthProvider>
      <DevAuthBanner />
      <BrowserRouter>
        <Routes>
          <Route path="/login" element={<LoginPage />} />
          <Route
            element={
              <AuthGuard>
                <AppLayout />
              </AuthGuard>
            }
          >
            <Route path="/connections" element={<ConnectionsPage />} />
            <Route path="/file-upload" element={<FileUploadPage />} />
          </Route>
          <Route path="/" element={<Navigate to="/connections" replace />} />
          <Route path="*" element={<Navigate to="/connections" replace />} />
        </Routes>
      </BrowserRouter>
    </AuthProvider>
  )
}

export default App
