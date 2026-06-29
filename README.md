# Deadstock Inventory Management System

A web-based Deadstock Inventory Management System designed to manage unsold inventory (deadstock), track stock movement across branches and warehouse, and support sustainable allocation decisions such as recycling, reselling, donation, and disposal.

The system provides role-based access control, inventory tracking, reporting, and PDF report generation for monitoring stock flow.


## Project Overview

The project helps organizations manage excess or unsold inventory efficiently by centralizing stock tracking and allocation workflows.

Main objectives:

- Track branch-wise deadstock inventory
- Transfer stock to warehouse for processing
- Allocate stock for different reuse/disposal actions
- Generate reports for inventory monitoring
- Maintain sustainable inventory management practices


## Features

### Authentication

- Role-based login system  
- Forgot password with OTP verification via email  

### Inventory Management
 
- Add deadstock inventory entries  
- Transfer stock to warehouse  
- Track stock movement across workflow stages  

### Stock Allocation

Inventory can be allocated for:

- Recycle  
- Donate  
- Resell  
- Upcycle  
- Rebrand  
- Disposal  

### Reporting

- Branch-wise inventory reports  
- Allocation statistics tracking  
- Sustainability metrics  
- PDF report download support  

### Additional Features

- Archive deleted branch and warehouse records for history  
- Preserve deadstock records after branch deletion  
- Dashboard with inventory analytics and charts  


## Tech Stack

**Backend**

- Python  
- Flask  

**Database**

- MySQL  

**Frontend**

- HTML  
- CSS  
- JavaScript  
- Jinja2  
  

## Database Structure

Main tables used:

```text
HEAD
BRANCH
DEADSTOCK
WAREHOUSE
STOCK_ALLOCATION
REPORT
MATERIAL
CONTACTS
DELETED_BRANCH
```

Workflow:

```text
Branch → Deadstock → Warehouse → Stock Allocation → Report
```

---

## Key Functionalities

- Multi-role access management  
- Database relationships with foreign key constraints  
- Automatic report updates during stock allocation  
- Branch deletion handling with archival records  
- PDF report generation using ReportLab  
- OTP-based password recovery system  


## Project Structure

```text
Dead-Stock_Management_System/
│
├── app.py
├── templates/
├── static/
└── database/
```
