/**
 * DemoCoverPage — wraps DemoCover with router navigation.
 * Navigates to /app (the live upload app) when Enter is clicked.
 */

import { useNavigate } from 'react-router-dom';
import DemoCover from './DemoCover';

export default function DemoCoverPage() {
  const navigate = useNavigate();
  return <DemoCover onEnter={() => navigate('/app')} />;
}
