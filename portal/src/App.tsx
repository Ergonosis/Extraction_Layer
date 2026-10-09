import { BrowserRouter, Navigate, Route, Routes } from 'react-router-dom'
import { AuthGuard } from './components/AuthGuard'
import { DevAuthBanner } from './components/DevAuthBanner'
import { AuthProvider } from './context/AuthContext'
import { ToastProvider } from './context/ToastContext'
import { AppLayout } from './layouts/AppLayout'
import { ConnectionsPage } from './pages/ConnectionsPage'
import { FileUploadPage } from './pages/FileUploadPage'
import { LoginPage } from './pages/LoginPage'
import './App.css'

function App() {
  return (
    <AuthProvider>
      <ToastProvider>
        <div className="app-frame">
          <DevAuthBanner />
          <div className="app-frame-body">
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
          </div>
        </div>
      </ToastProvider>
    </AuthProvider>
  )
}

export default App
