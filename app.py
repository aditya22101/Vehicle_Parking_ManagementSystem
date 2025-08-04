from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timedelta
import MySQLdb.cursors
import re

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = '2155'
app.config['MYSQL_DB'] = 'parking_app'

mysql = MySQL(app)

# Make datetime available in all templates
@app.context_processor
def inject_now():
    return {'now': datetime.now()}

def check_expired_bookings():
    """Check and update expired bookings"""
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Find expired bookings
    cursor.execute('''
        SELECT b.*, p.price_per_hour 
        FROM bookings b
        JOIN parking_lots p ON b.parking_lot_id = p.id
        WHERE b.status = 'active' AND b.end_time <= NOW()
    ''')
    expired_bookings = cursor.fetchall()
    
    for booking in expired_bookings:
        # Calculate actual duration and cost
        actual_start = booking['actual_start_time'] or booking['start_time']
        actual_end = datetime.now()
        
        # Calculate duration in minutes
        duration_minutes = (actual_end - actual_start).total_seconds() / 60
        # Round up to nearest hour for billing
        duration_hours = max(1, int((duration_minutes + 59) / 60))  # Round up
        
        actual_cost = booking['price_per_hour'] * duration_hours
        
        # Update booking as completed with actual cost
        cursor.execute('''
            UPDATE bookings 
            SET status = 'completed', 
                actual_end_time = %s,
                actual_cost = %s,
                updated_at = NOW()
            WHERE id = %s
        ''', (actual_end, actual_cost, booking['id']))
        
        # Free up the parking slot
        cursor.execute('''
            UPDATE parking_slots 
            SET status = 'vacant', booking_id = NULL 
            WHERE booking_id = %s
        ''', (booking['id'],))
    
    mysql.connection.commit()
    cursor.close()
    return len(expired_bookings)

def require_admin():
    """Decorator function to require admin authentication"""
    if 'admin_logged_in' not in session or not session.get('admin_logged_in'):
        flash('Admin access required!', 'error')
        return redirect(url_for('admin_login'))
    return None

def require_user():
    """Decorator function to require user authentication"""
    if 'logged_in' not in session or not session.get('logged_in'):
        flash('Please login to access this page!', 'error')
        return redirect(url_for('login'))
    return None

def is_user_logged_in():
    """Check if user is already logged in"""
    return 'logged_in' in session and session.get('logged_in') == True

def is_admin_logged_in():
    """Check if admin is already logged in"""
    return 'admin_logged_in' in session and session.get('admin_logged_in') == True

# Home route
@app.route('/')
def index():
    # Check for expired bookings on each page load
    check_expired_bookings()
    return render_template('index.html')

# Admin Login
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    # If admin is already logged in, redirect to dashboard
    if is_admin_logged_in():
        flash('You are already logged in as admin!', 'info')
        return redirect(url_for('admin_dashboard'))
    
    # If user is logged in, prevent admin login
    if is_user_logged_in():
        flash('Please logout from user account first to access admin panel!', 'error')
        return redirect(url_for('user_dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        if username == 'admin' and password == 'admin123':
            # Clear any existing session data
            session.clear()
            
            # Set admin session
            session['admin_logged_in'] = True
            session['admin_username'] = username
            session['user_type'] = 'admin'
            flash('Admin login successful!', 'success')
            return redirect(url_for('admin_dashboard'))
        else:
            flash('Invalid admin credentials!', 'error')
    
    return render_template('admin/login.html')

# Admin Dashboard
@app.route('/admin/dashboard')
def admin_dashboard():
    # Check admin authentication
    auth_check = require_admin()
    if auth_check:
        return auth_check
    
    # Check expired bookings
    expired_count = check_expired_bookings()
    if expired_count > 0:
        flash(f'{expired_count} expired bookings have been processed.', 'info')
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get parking lots with slot counts (only count non-deleted slots)
    cursor.execute('''
        SELECT p.*, 
               COUNT(CASE WHEN ps.deleted_at IS NULL THEN ps.id END) as total_slots,
               SUM(CASE WHEN ps.status = 'vacant' AND ps.deleted_at IS NULL THEN 1 ELSE 0 END) as available_slots,
               SUM(CASE WHEN ps.status = 'booked' AND ps.deleted_at IS NULL THEN 1 ELSE 0 END) as occupied_slots
        FROM parking_lots p
        LEFT JOIN parking_slots ps ON p.id = ps.parking_lot_id
        WHERE p.deleted_at IS NULL
        GROUP BY p.id
        ORDER BY p.created_at DESC
    ''')
    parking_lots = cursor.fetchall()
    
    # Get dashboard statistics (only count non-deleted items)
    cursor.execute('SELECT COUNT(*) as total_lots FROM parking_lots WHERE deleted_at IS NULL')
    total_lots = cursor.fetchone()['total_lots']
    
    cursor.execute('''
        SELECT COUNT(*) as total_slots 
        FROM parking_slots 
        WHERE deleted_at IS NULL
    ''')
    total_slots_result = cursor.fetchone()
    total_slots = total_slots_result['total_slots'] if total_slots_result['total_slots'] else 0
    
    cursor.execute('''
        SELECT COUNT(*) as available_slots 
        FROM parking_slots 
        WHERE status = 'vacant' AND deleted_at IS NULL
    ''')
    available_slots_result = cursor.fetchone()
    available_slots = available_slots_result['available_slots'] if available_slots_result['available_slots'] else 0
    
    cursor.execute('SELECT COUNT(*) as active_bookings FROM bookings WHERE status = "active"')
    active_bookings = cursor.fetchone()['active_bookings']
    
    # Calculate revenue from completed bookings only
    cursor.execute('''
        SELECT SUM(actual_cost) as total_revenue 
        FROM bookings 
        WHERE status = 'completed' AND actual_cost IS NOT NULL
    ''')
    revenue_result = cursor.fetchone()
    total_revenue = revenue_result['total_revenue'] if revenue_result['total_revenue'] else 0
    
    # Monthly revenue data for chart (completed bookings only)
    cursor.execute('''
        SELECT 
            DATE_FORMAT(actual_end_time, '%Y-%m') as month,
            SUM(actual_cost) as revenue
        FROM bookings 
        WHERE status = 'completed' AND actual_cost IS NOT NULL
        GROUP BY DATE_FORMAT(actual_end_time, '%Y-%m')
        ORDER BY month DESC
        LIMIT 6
    ''')
    monthly_revenue = cursor.fetchall()
    
    cursor.close()
    
    stats = {
        'total_lots': total_lots,
        'total_slots': total_slots,
        'available_slots': available_slots,
        'occupied_slots': total_slots - available_slots,
        'active_bookings': active_bookings,
        'total_revenue': total_revenue,
        'monthly_revenue': monthly_revenue
    }
    
    return render_template('admin/dashboard.html', parking_lots=parking_lots, stats=stats)

# Add Parking Lot
@app.route('/admin/add-parking-lot', methods=['GET', 'POST'])
def add_parking_lot():
    # Check admin authentication
    auth_check = require_admin()
    if auth_check:
        return auth_check
    
    if request.method == 'POST':
        name = request.form['name']
        location = request.form['location']
        total_slots = int(request.form['total_slots'])
        price_per_hour = float(request.form['price_per_hour'])
        
        cursor = mysql.connection.cursor()
        
        # Create parking lot
        cursor.execute('''
            INSERT INTO parking_lots (name, location, price_per_hour)
            VALUES (%s, %s, %s)
        ''', (name, location, price_per_hour))
        
        lot_id = cursor.lastrowid
        
        # Create individual parking slots
        for slot_number in range(1, total_slots + 1):
            cursor.execute('''
                INSERT INTO parking_slots (parking_lot_id, slot_number, status)
                VALUES (%s, %s, 'vacant')
            ''', (lot_id, slot_number))
        
        mysql.connection.commit()
        cursor.close()
        
        flash(f'Parking lot "{name}" with {total_slots} slots added successfully!', 'success')
        return redirect(url_for('admin_dashboard'))
    
    return render_template('admin/add_parking_lot.html')

# Admin: View All Bookings
@app.route('/admin/bookings')
def admin_bookings():
    # Check admin authentication
    auth_check = require_admin()
    if auth_check:
        return auth_check
    
    # Check expired bookings
    check_expired_bookings()
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT b.*, u.username, u.email, u.phone, 
               p.name as parking_lot_name, p.location,
               ps.slot_number
        FROM bookings b
        JOIN users u ON b.user_id = u.id
        JOIN parking_lots p ON b.parking_lot_id = p.id
        LEFT JOIN parking_slots ps ON b.slot_id = ps.id
        ORDER BY b.created_at DESC
    ''')
    bookings = cursor.fetchall()
    cursor.close()
    
    return render_template('admin/bookings.html', bookings=bookings)

# Admin: Cancel Any Booking
@app.route('/admin/cancel-booking/<int:booking_id>')
def admin_cancel_booking(booking_id):
    # Check admin authentication
    auth_check = require_admin()
    if auth_check:
        return auth_check
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT b.*, p.price_per_hour 
        FROM bookings b
        JOIN parking_lots p ON b.parking_lot_id = p.id
        WHERE b.id = %s AND b.status = 'active'
    ''', (booking_id,))
    booking = cursor.fetchone()
    
    if booking:
        # Calculate cost for time used (if any)
        actual_cost = 0
        if booking['actual_start_time']:
            duration_minutes = (datetime.now() - booking['actual_start_time']).total_seconds() / 60
            if duration_minutes > 0:
                duration_hours = max(1, int((duration_minutes + 59) / 60))  # Round up
                actual_cost = booking['price_per_hour'] * duration_hours
        
        # Cancel booking
        cursor.execute('''
            UPDATE bookings 
            SET status = 'cancelled', 
                actual_end_time = NOW(),
                actual_cost = %s,
                updated_at = NOW()
            WHERE id = %s
        ''', (actual_cost, booking_id))
        
        # Free up the parking slot
        if booking['slot_id']:
            cursor.execute('''
                UPDATE parking_slots 
                SET status = 'vacant', booking_id = NULL 
                WHERE id = %s
            ''', (booking['slot_id'],))
        
        mysql.connection.commit()
        flash('Booking cancelled successfully!', 'success')
    else:
        flash('Booking not found or already cancelled!', 'error')
    
    cursor.close()
    return redirect(url_for('admin_bookings'))

# Admin: Soft Delete Parking Lot
@app.route('/admin/delete-parking-lot/<int:lot_id>')
def delete_parking_lot(lot_id):
    # Check admin authentication
    auth_check = require_admin()
    if auth_check:
        return auth_check
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if there are active bookings
    cursor.execute('''
        SELECT COUNT(*) as count 
        FROM bookings b
        JOIN parking_slots ps ON b.slot_id = ps.id
        WHERE ps.parking_lot_id = %s AND b.status = 'active'
    ''', (lot_id,))
    active_bookings = cursor.fetchone()
    
    if active_bookings['count'] > 0:
        flash('Cannot delete parking lot with active bookings!', 'error')
    else:
        # Soft delete the parking lot and all its slots
        cursor.execute('''
            UPDATE parking_lots 
            SET deleted_at = NOW() 
            WHERE id = %s
        ''', (lot_id,))
        
        cursor.execute('''
            UPDATE parking_slots 
            SET deleted_at = NOW(), status = 'deleted'
            WHERE parking_lot_id = %s AND deleted_at IS NULL
        ''', (lot_id,))
        
        mysql.connection.commit()
        flash('Parking lot and all its slots deleted successfully!', 'success')
    
    cursor.close()
    return redirect(url_for('admin_dashboard'))

# Admin: Restore Parking Lot
@app.route('/admin/restore-parking-lot/<int:lot_id>')
def restore_parking_lot(lot_id):
    # Check admin authentication
    auth_check = require_admin()
    if auth_check:
        return auth_check
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if parking lot is deleted
    cursor.execute('''
        SELECT * FROM parking_lots 
        WHERE id = %s AND deleted_at IS NOT NULL
    ''', (lot_id,))
    parking_lot = cursor.fetchone()
    
    if parking_lot:
        # Restore the parking lot
        cursor.execute('''
            UPDATE parking_lots 
            SET deleted_at = NULL 
            WHERE id = %s
        ''', (lot_id,))
        
        # Restore all slots that were deleted with this lot
        cursor.execute('''
            UPDATE parking_slots 
            SET deleted_at = NULL, status = 'vacant'
            WHERE parking_lot_id = %s AND status = 'deleted'
        ''', (lot_id,))
        
        mysql.connection.commit()
        flash(f'Parking lot "{parking_lot["name"]}" and all its slots restored successfully!', 'success')
    else:
        flash('Parking lot not found or not deleted!', 'error')
    
    cursor.close()
    return redirect(url_for('admin_dashboard'))

# Admin: View Deleted Parking Lots
@app.route('/admin/deleted-lots')
def admin_deleted_lots():
    # Check admin authentication
    auth_check = require_admin()
    if auth_check:
        return auth_check
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get deleted parking lots with slot counts
    cursor.execute('''
        SELECT p.*, 
               COUNT(ps.id) as total_slots,
               p.deleted_at as deletion_date
        FROM parking_lots p
        LEFT JOIN parking_slots ps ON p.id = ps.parking_lot_id
        WHERE p.deleted_at IS NOT NULL
        GROUP BY p.id
        ORDER BY p.deleted_at DESC
    ''')
    deleted_lots = cursor.fetchall()
    
    cursor.close()
    
    return render_template('admin/deleted_lots.html', deleted_lots=deleted_lots)

# Admin: View Parking Slots Details
@app.route('/admin/parking-slots/<int:lot_id>')
def admin_parking_slots(lot_id):
    # Check admin authentication
    auth_check = require_admin()
    if auth_check:
        return auth_check
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get parking lot details
    cursor.execute('''
        SELECT * FROM parking_lots 
        WHERE id = %s AND deleted_at IS NULL
    ''', (lot_id,))
    parking_lot = cursor.fetchone()
    
    if not parking_lot:
        flash('Parking lot not found!', 'error')
        return redirect(url_for('admin_dashboard'))
    
    # Get all slots for this parking lot (including deleted ones for admin view)
    cursor.execute('''
        SELECT ps.*, b.id as booking_id, b.vehicle_number, b.vehicle_type,
               b.start_time, b.end_time, u.username, u.email, u.phone
        FROM parking_slots ps
        LEFT JOIN bookings b ON ps.booking_id = b.id AND b.status = 'active'
        LEFT JOIN users u ON b.user_id = u.id
        WHERE ps.parking_lot_id = %s
        ORDER BY ps.slot_number
    ''', (lot_id,))
    parking_slots = cursor.fetchall()
    
    cursor.close()
    
    return render_template('admin/parking_slots.html', 
                         parking_lot=parking_lot, 
                         parking_slots=parking_slots)

# Admin: Delete Individual Slot
@app.route('/admin/delete-slot/<int:slot_id>')
def delete_parking_slot(slot_id):
    # Check admin authentication
    auth_check = require_admin()
    if auth_check:
        return auth_check
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if slot has active booking
    cursor.execute('''
        SELECT ps.*, b.status
        FROM parking_slots ps
        LEFT JOIN bookings b ON ps.booking_id = b.id
        WHERE ps.id = %s
    ''', (slot_id,))
    slot = cursor.fetchone()
    
    if slot and slot['status'] == 'active':
        flash('Cannot delete slot with active booking!', 'error')
    else:
        # Soft delete the slot
        cursor.execute('''
            UPDATE parking_slots 
            SET deleted_at = NOW(), status = 'deleted'
            WHERE id = %s
        ''', (slot_id,))
        mysql.connection.commit()
        flash(f'Parking slot #{slot["slot_number"]} deleted successfully!', 'success')
    
    cursor.close()
    return redirect(request.referrer or url_for('admin_dashboard'))

# Admin: Restore Individual Slot
@app.route('/admin/restore-slot/<int:slot_id>')
def restore_parking_slot(slot_id):
    # Check admin authentication
    auth_check = require_admin()
    if auth_check:
        return auth_check
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if slot is deleted
    cursor.execute('''
        SELECT * FROM parking_slots 
        WHERE id = %s AND deleted_at IS NOT NULL
    ''', (slot_id,))
    slot = cursor.fetchone()
    
    if slot:
        # Restore the slot
        cursor.execute('''
            UPDATE parking_slots 
            SET deleted_at = NULL, status = 'vacant', booking_id = NULL
            WHERE id = %s
        ''', (slot_id,))
        mysql.connection.commit()
        flash(f'Parking slot #{slot["slot_number"]} restored successfully!', 'success')
    else:
        flash('Slot not found or not deleted!', 'error')
    
    cursor.close()
    return redirect(request.referrer or url_for('admin_dashboard'))

# User Registration
@app.route('/register', methods=['GET', 'POST'])
def register():
    # If user is already logged in, redirect to dashboard
    if is_user_logged_in():
        flash('You are already logged in!', 'info')
        return redirect(url_for('user_dashboard'))
    
    # If admin is logged in, prevent user registration
    if is_admin_logged_in():
        flash('Please logout from admin account first!', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        phone = request.form['phone']
        
        # Validation
        if not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            flash('Invalid email address!', 'error')
            return render_template('register.html')
        
        if len(password) < 6:
            flash('Password must be at least 6 characters long!', 'error')
            return render_template('register.html')
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s OR email = %s', (username, email))
        account = cursor.fetchone()
        
        if account:
            flash('Account already exists!', 'error')
        else:
            hashed_password = generate_password_hash(password)
            cursor.execute('''
                INSERT INTO users (username, email, password, phone)
                VALUES (%s, %s, %s, %s)
            ''', (username, email, hashed_password, phone))
            mysql.connection.commit()
            flash('Registration successful! Please login.', 'success')
            return redirect(url_for('login'))
        
        cursor.close()
    
    return render_template('register.html')

# User Login
@app.route('/login', methods=['GET', 'POST'])
def login():
    # If user is already logged in, redirect to dashboard
    if is_user_logged_in():
        flash('You are already logged in!', 'info')
        return redirect(url_for('user_dashboard'))
    
    # If admin is logged in, prevent user login
    if is_admin_logged_in():
        flash('Please logout from admin account first to access user login!', 'error')
        return redirect(url_for('admin_dashboard'))
    
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        account = cursor.fetchone()
        cursor.close()
        
        if account and check_password_hash(account['password'], password):
            # Clear any existing session data
            session.clear()
            
            # Set user session
            session['logged_in'] = True
            session['user_id'] = account['id']
            session['username'] = account['username']
            session['user_type'] = 'user'
            
            # Check for expired bookings and notify user
            expired_count = check_expired_bookings()
            if expired_count > 0:
                flash(f'You have {expired_count} booking(s) that have ended. Please check your booking history.', 'info')
            
            flash('Login successful!', 'success')
            return redirect(url_for('user_dashboard'))
        else:
            flash('Invalid username or password!', 'error')
    
    return render_template('login.html')

# User Dashboard
@app.route('/dashboard')
def user_dashboard():
    # Check user authentication
    auth_check = require_user()
    if auth_check:
        return auth_check
    
    # Check expired bookings
    check_expired_bookings()
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT p.*, 
               COUNT(CASE WHEN ps.deleted_at IS NULL THEN ps.id END) as total_slots,
               SUM(CASE WHEN ps.status = 'vacant' AND ps.deleted_at IS NULL THEN 1 ELSE 0 END) as available_slots
        FROM parking_lots p
        LEFT JOIN parking_slots ps ON p.id = ps.parking_lot_id
        WHERE p.deleted_at IS NULL
        GROUP BY p.id
        HAVING available_slots > 0
        ORDER BY p.name
    ''')
    parking_lots = cursor.fetchall()
    cursor.close()
    
    return render_template('user/dashboard.html', parking_lots=parking_lots)

# Book Parking Slot
@app.route('/book-slot/<int:lot_id>', methods=['GET', 'POST'])
def book_slot(lot_id):
    # Check user authentication
    auth_check = require_user()
    if auth_check:
        return auth_check
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get parking lot details
    cursor.execute('''
        SELECT * FROM parking_lots 
        WHERE id = %s AND deleted_at IS NULL
    ''', (lot_id,))
    parking_lot = cursor.fetchone()
    
    if not parking_lot:
        flash('Parking lot not found!', 'error')
        return redirect(url_for('user_dashboard'))
    
    # Get available slots (only non-deleted)
    cursor.execute('''
        SELECT * FROM parking_slots 
        WHERE parking_lot_id = %s AND status = 'vacant' AND deleted_at IS NULL
        ORDER BY slot_number
    ''', (lot_id,))
    available_slots = cursor.fetchall()
    
    if request.method == 'POST':
        vehicle_number = request.form['vehicle_number']
        vehicle_type = request.form['vehicle_type']
        hours = int(request.form['hours'])
        slot_id = int(request.form['slot_id'])
        
        if not available_slots:
            flash('No available slots!', 'error')
            return redirect(url_for('user_dashboard'))
        
        # Verify slot is still available
        cursor.execute('''
            SELECT * FROM parking_slots 
            WHERE id = %s AND status = 'vacant' AND deleted_at IS NULL
        ''', (slot_id,))
        selected_slot = cursor.fetchone()
        
        if not selected_slot:
            flash('Selected slot is no longer available!', 'error')
            return redirect(url_for('book_slot', lot_id=lot_id))
        
        estimated_cost = parking_lot['price_per_hour'] * hours
        start_time = datetime.now()
        end_time = start_time + timedelta(hours=hours)
        
        # Create booking (no actual cost yet)
        cursor.execute('''
            INSERT INTO bookings (user_id, parking_lot_id, slot_id, vehicle_number, vehicle_type, 
                                start_time, end_time, estimated_cost, status, actual_start_time)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'active', %s)
        ''', (session['user_id'], lot_id, slot_id, vehicle_number, vehicle_type, 
              start_time, end_time, estimated_cost, start_time))
        
        booking_id = cursor.lastrowid
        
        # Update slot status
        cursor.execute('''
            UPDATE parking_slots 
            SET status = 'booked', booking_id = %s 
            WHERE id = %s
        ''', (booking_id, slot_id))
        
        mysql.connection.commit()
        cursor.close()
        
        flash(f'Parking slot #{selected_slot["slot_number"]} booked successfully!', 'success')
        return redirect(url_for('my_bookings'))
    
    cursor.close()
    return render_template('user/book_slot.html', 
                         parking_lot=parking_lot, 
                         available_slots=available_slots)

# My Bookings
@app.route('/my-bookings')
def my_bookings():
    # Check user authentication
    auth_check = require_user()
    if auth_check:
        return auth_check
    
    # Check expired bookings
    check_expired_bookings()
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT b.*, p.name as parking_lot_name, p.location,
               ps.slot_number
        FROM bookings b
        JOIN parking_lots p ON b.parking_lot_id = p.id
        LEFT JOIN parking_slots ps ON b.slot_id = ps.id
        WHERE b.user_id = %s
        ORDER BY b.created_at DESC
    ''', (session['user_id'],))
    bookings = cursor.fetchall()
    cursor.close()
    
    return render_template('user/my_bookings.html', bookings=bookings)

# Cancel Booking
@app.route('/cancel-booking/<int:booking_id>')
def cancel_booking(booking_id):
    # Check user authentication
    auth_check = require_user()
    if auth_check:
        return auth_check
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('''
        SELECT b.*, p.price_per_hour 
        FROM bookings b
        JOIN parking_lots p ON b.parking_lot_id = p.id
        WHERE b.id = %s AND b.user_id = %s AND b.status = 'active'
    ''', (booking_id, session['user_id']))
    booking = cursor.fetchone()
    
    if booking:
        # Calculate cost for time used (if any)
        actual_cost = 0
        if booking['actual_start_time']:
            duration_minutes = (datetime.now() - booking['actual_start_time']).total_seconds() / 60
            if duration_minutes > 0:
                duration_hours = max(1, int((duration_minutes + 59) / 60))  # Round up
                actual_cost = booking['price_per_hour'] * duration_hours
        
        # Cancel booking
        cursor.execute('''
            UPDATE bookings 
            SET status = 'cancelled', 
                actual_end_time = NOW(),
                actual_cost = %s,
                updated_at = NOW()
            WHERE id = %s
        ''', (actual_cost, booking_id))
        
        # Free up the parking slot
        if booking['slot_id']:
            cursor.execute('''
                UPDATE parking_slots 
                SET status = 'vacant', booking_id = NULL 
                WHERE id = %s
            ''', (booking['slot_id'],))
        
        mysql.connection.commit()
        flash('Booking cancelled successfully!', 'success')
    else:
        flash('Booking not found or already cancelled!', 'error')
    
    cursor.close()
    return redirect(url_for('my_bookings'))

# Logout routes
@app.route('/logout')
def logout():
    user_type = session.get('user_type', 'unknown')
    session.clear()
    flash(f'You have been logged out successfully!', 'info')
    return redirect(url_for('index'))

@app.route('/admin/logout')
def admin_logout():
    session.clear()
    flash('Admin logged out successfully!', 'info')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)
