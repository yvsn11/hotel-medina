import { Route, Routes } from 'react-router-dom';
import { Layout } from './components/Layout';
import { RequireAuth, RequireStaff } from './components/Guards';
import Home from './pages/Home';
import Book from './pages/Book';
import Pay from './pages/Pay';
import Bookings from './pages/Bookings';
import Login from './pages/Login';
import Register from './pages/Register';
import Staff from './pages/Staff';
import NotFound from './pages/NotFound';

export default function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route path="/" element={<Home />} />
        <Route path="/login" element={<Login />} />
        <Route path="/register" element={<Register />} />
        <Route element={<RequireAuth />}>
          <Route path="/book" element={<Book />} />
          <Route path="/bookings" element={<Bookings />} />
          <Route path="/bookings/:id/pay" element={<Pay />} />
        </Route>
        <Route element={<RequireStaff />}>
          <Route path="/staff" element={<Staff />} />
        </Route>
        <Route path="*" element={<NotFound />} />
      </Route>
    </Routes>
  );
}
