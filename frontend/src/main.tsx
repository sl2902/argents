import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom'
import './index.css'
import App from './App'
import DemoCoverPage from './pages/DemoCoverPage'
import PipelineExplainer from './pages/PipelineExplainer'
import ResultsWalkthrough from './pages/ResultsWalkthrough'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Routes>
        <Route path="/" element={<DemoCoverPage />} />
        <Route path="/app" element={<App />} />
        <Route path="/demo/explainer" element={<PipelineExplainer />} />
        <Route path="/demo/results" element={<ResultsWalkthrough />} />
        {/* Legacy /demo redirects to cover */}
        <Route path="/demo" element={<Navigate to="/" replace />} />
      </Routes>
    </BrowserRouter>
  </StrictMode>,
)
