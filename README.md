# Vehicle_Parking_ManagementSystem
ParkEasy – Vehicle Parking Management Software. ParkEasy is a web-based parking management system that is built on the Flask (Python) framework and SQL. ParkEasy allow users to book real-time parking slots and provide an admin dashboard to manage lots, slots and bookings.
Vehicle Parking Management System

A comprehensive, production-ready parking management system built with Flask, MySQL, and Bootstrap featuring realistic billing, individual slot management, and intelligent booking lifecycle.

Problem Statement & Solutions

**Core Problems Addressed**

**Problem 1: Unrealistic Revenue System**
**Issue:** Original system calculated revenue immediately upon booking, which is unrealistic for parking systems.

**Solution Implemented:**
- Revenue calculated only after booking completion or cancellation
- Dynamic billing based on actual usage time (rounded up to nearest hour)
- Separate tracking of `estimated_cost` vs `actual_cost`
- Time-based billing with `actual_start_time` and `actual_end_time`

**Problem 2: No Automatic Booking Expiration**
**Issue:** Bookings never expired automatically, leading to permanently occupied slots.

**Solution Implemented:**
-Automatic detection of expired bookings on each page load
- Auto-completion of expired bookings with proper cost calculation
- Automatic slot liberation when bookings expire
- User notifications for expired bookings on login

**Problem 3: Generic Slot Management**
**Issue:** Parking lots only tracked total/available slots without individual slot identification.

**Solution Implemented:**
-  Individual numbered parking slots with unique IDs
-  Visual slot selection interface for users
-  Color-coded slot status (Green=Vacant, Purple=Booked, Black=Deleted)
-  Detailed occupancy tracking with user information per slot

**Problem 4: Hard Deletion & Data Loss**
**Issue:** Deleting parking lots/slots permanently removed data, losing historical information.

**Solution Implemented:**
- Soft deletion system preserving historical data
- Admin-only deletion privileges with safety checks
- Cannot delete lots/slots with active bookings
- Deleted items marked with `deleted_at` timestamp

**Problem 5: Poor User Experience**
**Issue:** Limited booking management and unclear cost structure.

**Solution Implemented:**
- Interactive slot selection with visual feedback
- Real-time cost calculation and updates
- Comprehensive booking history with actual vs estimated costs
- Clear booking status indicators and notifications

**System Architecture**

**Database Schema**

**Enhanced Tables:**
1. **`users`** - User authentication and profile management
2. **`parking_lots`** - Parking facility information with soft deletion
3. **`parking_slots`** - Individual numbered slots per parking lot
4. **`bookings`** - Enhanced booking tracking with actual cost calculation

**Key Relationships:**
- One parking lot → Many parking slots
- One parking slot → One active booking (at most)
- One user → Many bookings
- Soft deletion preserves referential integrity

**Core Features**

**👤 User Features:**
- **Registration & Authentication** - Secure user account management
- **Visual Slot Selection** - Interactive parking slot booking interface
- **Real-time Pricing** - Dynamic cost calculation based on duration
- **Booking Management** - View, track, and cancel bookings
- **Cost Transparency** - See estimated vs actual costs
- **Automatic Notifications** - Alerts for expired bookings

**👨‍💼 Admin Features:**
- **Dashboard Analytics** - Revenue tracking, occupancy statistics
- **Parking Lot Management** - Add, view, and soft-delete parking facilities
- **Individual Slot Control** - Manage and delete specific parking slots
- **Booking Oversight** - View all bookings, cancel any booking
- **Visual Slot Layout** - See real-time occupancy with user details
- **Revenue Reports** - Track actual revenue from completed bookings only

**🤖 System Intelligence:**
- **Automatic Expiration Detection** - Processes expired bookings automatically
- **Dynamic Cost Calculation** - Bills based on actual usage time
- **Slot Status Management** - Real-time updates of slot availability
- **Data Integrity Protection** - Prevents deletion of active bookings

**Installation & Setup**

**Prerequisites**
- Python 3.8+
- MySQL 8.0+
- pip (Python package manager)

**Step 1: Clone Repository**
\`\`\`bash
git clonegit@github.com:aditya22101/Vehicle_Parking_ManagementSystem.git
\`\`\`

**Step 2: Install Dependencies**
\`\`\`
pip install -r requirements.txt
\`\`\`

**Step 3: Database Setup**
1. Install and start MySQL server
2. Create database:
   \`\`\`sql
   CREATE DATABASE parking_app;
   \`\`\`
3. Run the enhanced database setup:
   \`\`\`bash
   mysql -u root -p parking_app < scripts/enhanced_database_setup.sql
   \`\`\`

**Step 4: Configure Database Connection**
Update MySQL credentials in `app.py`:
```python
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'your_username'
app.config['MYSQL_PASSWORD'] = 'your_password'
app.config['MYSQL_DB'] = 'parking_app'
