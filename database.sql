
-- DEADSTOCK INVENTORY MANAGEMENT SYSTEM
-- Complete Database Setup

CREATE DATABASE deadstock_db;

USE deadstock_db;


-- ADMIN

CREATE TABLE ADMIN (
  Admin_ID INT          NOT NULL AUTO_INCREMENT,
  Username VARCHAR(50)  NOT NULL UNIQUE,
  Password VARCHAR(255) NOT NULL,
  PRIMARY KEY (Admin_ID)
);


-- HEAD

CREATE TABLE HEAD (
  Head_ID  INT          NOT NULL AUTO_INCREMENT,
  Name     VARCHAR(100) NOT NULL,
  Email    VARCHAR(150) NOT NULL UNIQUE,
  Status   ENUM('Branch','Warehouse','Stock_Allocation') NOT NULL,
  Password VARCHAR(255) NOT NULL,
  PRIMARY KEY (Head_ID)
);


-- CONTACTS  (10-digit validation enforced in app.py)

CREATE TABLE CONTACTS (
  Contact_ID INT         NOT NULL AUTO_INCREMENT,
  Head_ID    INT         NOT NULL,
  Contact_no VARCHAR(15) NOT NULL,
  PRIMARY KEY (Contact_ID),
  FOREIGN KEY (Head_ID) REFERENCES HEAD(Head_ID) ON DELETE CASCADE
);


-- MATERIAL

CREATE TABLE MATERIAL (
  Material_ID            INT          NOT NULL AUTO_INCREMENT,
  Material_Name          VARCHAR(100) NOT NULL,
  Sustainability_Quality ENUM('High','Medium','Low') NOT NULL DEFAULT 'Medium',
  PRIMARY KEY (Material_ID)
);


-- WAREHOUSE

CREATE TABLE WAREHOUSE (
  Warehouse_ID INT          NOT NULL AUTO_INCREMENT,
  Head_ID      INT          NOT NULL,
  City         VARCHAR(100) NOT NULL,
  Last_Audit   DATE         NOT NULL DEFAULT (CURDATE()),
  Capacity     INT          NOT NULL DEFAULT 0,
  PRIMARY KEY (Warehouse_ID),
  FOREIGN KEY (Head_ID) REFERENCES HEAD(Head_ID) ON DELETE RESTRICT
);


-- BRANCH  (Sustainable_Rating nullable; auto-updated by trigger)

CREATE TABLE BRANCH (
  Branch_ID          INT          NOT NULL AUTO_INCREMENT,
  Warehouse_ID       INT          NOT NULL,
  Head_ID            INT          NOT NULL,
  City               VARCHAR(100) NOT NULL,
  Last_Audit         DATE         NOT NULL DEFAULT (CURDATE()),
  Sustainable_Rating DECIMAL(3,1) DEFAULT NULL,
  PRIMARY KEY (Branch_ID),
  FOREIGN KEY (Warehouse_ID) REFERENCES WAREHOUSE(Warehouse_ID) ON DELETE RESTRICT,
  FOREIGN KEY (Head_ID)      REFERENCES HEAD(Head_ID)            ON DELETE RESTRICT
);


-- DEADSTOCK

CREATE TABLE DEADSTOCK (
  Deadstock_ID      INT  NOT NULL AUTO_INCREMENT,
  Branch_ID         INT  NOT NULL,
  Category          VARCHAR(100) NOT NULL,
  Size              ENUM('XS','S','M','L','XL','XXL') NOT NULL DEFAULT 'M',
  Material_ID       INT  NOT NULL,
  Quantity          INT  NOT NULL DEFAULT 0,
  Sent_To_Warehouse TINYINT(1) NOT NULL DEFAULT 0,
  Sent_To_SA        TINYINT(1) NOT NULL DEFAULT 0,
  Allocated_Type    ENUM('Recycle','Donate','Resell','Upcycle','Rebrand','Disposal') DEFAULT NULL,
  PRIMARY KEY (Deadstock_ID),
  FOREIGN KEY (Branch_ID)   REFERENCES BRANCH(Branch_ID)     ON DELETE RESTRICT,
  FOREIGN KEY (Material_ID) REFERENCES MATERIAL(Material_ID) ON DELETE RESTRICT
);


-- STOCK_ALLOCATION

CREATE TABLE STOCK_ALLOCATION (
  Allocation_ID   INT  NOT NULL AUTO_INCREMENT,
  Deadstock_ID    INT  NOT NULL,
  Head_ID         INT  NOT NULL,
  Allocation_Type ENUM('Recycle','Donate','Resell','Upcycle','Rebrand','Disposal') NOT NULL,
  Quantity        INT  NOT NULL DEFAULT 0,
  Allocated_At    TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,
  PRIMARY KEY (Allocation_ID),
  UNIQUE KEY uq_deadstock (Deadstock_ID),
  FOREIGN KEY (Deadstock_ID) REFERENCES DEADSTOCK(Deadstock_ID) ON DELETE CASCADE,
  FOREIGN KEY (Head_ID)      REFERENCES HEAD(Head_ID)            ON DELETE RESTRICT
);

-- REPORT  (one per branch)

CREATE TABLE REPORT (
  Report_ID               INT           NOT NULL AUTO_INCREMENT,
  Branch_ID               INT           NOT NULL UNIQUE,
  Items_Resold            INT           NOT NULL DEFAULT 0,
  Items_Recycled          INT           NOT NULL DEFAULT 0,
  Items_Donated           INT           NOT NULL DEFAULT 0,
  Items_Upcycled          INT           NOT NULL DEFAULT 0,
  Items_Rebranded         INT           NOT NULL DEFAULT 0,
  Items_Disposed          INT           NOT NULL DEFAULT 0,
  Estimated_Waste_Reduced DECIMAL(10,2) NOT NULL DEFAULT 0.00,
  PRIMARY KEY (Report_ID),
  FOREIGN KEY (Branch_ID) REFERENCES BRANCH(Branch_ID) ON DELETE CASCADE
);


-- DELETED_BRANCH  (soft-delete archive)

CREATE TABLE DELETED_BRANCH (
  Branch_ID          INT,
  Warehouse_ID       INT,
  Head_ID            INT,
  City               VARCHAR(100),
  Last_Audit         DATE,
  Sustainable_Rating DECIMAL(3,1),
  Deleted_At         TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- DELETED_WAREHOUSE  (soft-delete archive)

CREATE TABLE DELETED_WAREHOUSE (
  Warehouse_ID INT,
  Head_ID      INT,
  City         VARCHAR(100),
  Last_Audit   DATE,
  Capacity     INT,
  Deleted_At   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP
);


-- TRIGGER: trg_update_branch_rating
-- Fires BEFORE INSERT on STOCK_ALLOCATION
-- Upcycle +0.3 | Recycle +0.2 | Rebrand +0.1 | Donate +0.1
-- Resell no change | Disposal -0.3


DELIMITER $$
CREATE TRIGGER trg_update_branch_rating
BEFORE INSERT ON STOCK_ALLOCATION
FOR EACH ROW
BEGIN
  DECLARE v_branch_id INT;
  DECLARE v_current   DECIMAL(3,1);
  DECLARE v_new       DECIMAL(3,1);

  SELECT Branch_ID INTO v_branch_id
  FROM   DEADSTOCK WHERE Deadstock_ID = NEW.Deadstock_ID;

  SELECT IFNULL(Sustainable_Rating, 3.0) INTO v_current
  FROM   BRANCH WHERE Branch_ID = v_branch_id;

  SET v_new = CASE NEW.Allocation_Type
    WHEN 'Upcycle'  THEN LEAST(5.0,    v_current + 0.3)
    WHEN 'Recycle'  THEN LEAST(5.0,    v_current + 0.2)
    WHEN 'Rebrand'  THEN LEAST(5.0,    v_current + 0.1)
    WHEN 'Donate'   THEN LEAST(5.0,    v_current + 0.1)
    WHEN 'Resell'   THEN               v_current
    WHEN 'Disposal' THEN GREATEST(0.0, v_current - 0.3)
    ELSE                               v_current
  END;

  UPDATE BRANCH SET Sustainable_Rating = v_new WHERE Branch_ID = v_branch_id;
END$$
DELIMITER ;


-- INSERT SOME HARDCODED DATA

INSERT INTO ADMIN (Username, Password) VALUES ('admin', 'admin123');

INSERT INTO MATERIAL (Material_Name, Sustainability_Quality) VALUES
  ('Cotton',          'High'),
  ('Polyester',       'Low'),
  ('Linen',           'High'),
  ('Nylon',           'Medium'),
  ('Wool',            'High'),
  ('Rayon / Viscose', 'Medium'),
  ('Spandex',         'Low'),
  ('Silk',            'Medium');

INSERT INTO HEAD (Name, Email, Status, Password) VALUES
  ('Priya Sharma',  'priya@company.com',  'Warehouse',        'pass1234'),
  ('Rohan Mehta',   'rohan@company.com',  'Warehouse',        'pass1234'),
  ('Aditi Joshi',   'aditi@company.com',  'Branch',           'pass1234'),
  ('Sameer Khan',   'sameer@company.com', 'Branch',           'pass1234'),
  ('Neha Gupta',    'neha@company.com',   'Branch',           'pass1234'),
  ('Kiran Patil',   'kiran@company.com',  'Stock_Allocation', 'pass1234');

INSERT INTO CONTACTS (Head_ID, Contact_no) VALUES
  (1, '9876543210'), (2, '9123456780'),
  (3, '9012345678'), (4, '9988776655'),
  (5, '9871234560'), (6, '9765432100');


INSERT INTO WAREHOUSE (Head_ID, City, Last_Audit, Capacity) VALUES
  (1, 'Mumbai', CURDATE(), 5000),
  (2, 'Delhi',  CURDATE(), 4000);

INSERT INTO BRANCH (Warehouse_ID, Head_ID, City, Last_Audit, Sustainable_Rating) VALUES
  (1, 3, 'Pune',   CURDATE(), 3.5),
  (1, 4, 'Nashik', CURDATE(), 3.0),
  (2, 5, 'Jaipur', CURDATE(), 4.0);

INSERT INTO DEADSTOCK (Branch_ID,Category,Size,Material_ID,Quantity,Sent_To_Warehouse,Sent_To_SA) VALUES
  (1,'T-Shirts','M',  1,120,0,0),
  (1,'Jeans',   'L',  2, 80,0,0),
  (2,'Kurtas',  'XL', 3, 60,0,0),
  (2,'Jackets', 'S',  4, 40,0,0),
  (3,'Sarees',  'M',  5, 50,0,0),
  (3,'Trousers','XXL',2, 30,0,0);

INSERT INTO REPORT
  (Branch_ID,Items_Resold,Items_Recycled,Items_Donated,
   Items_Upcycled,Items_Rebranded,Items_Disposed,Estimated_Waste_Reduced)
VALUES
  (1,0,0,0,0,0,0,0.00),
  (2,0,0,0,0,0,0,0.00),
  (3,0,0,0,0,0,0,0.00);


SHOW TRIGGERS FROM deadstock_db;


-- Find the current FK name on DEADSTOCK.Branch_ID:
SELECT CONSTRAINT_NAME
FROM INFORMATION_SCHEMA.KEY_COLUMN_USAGE
WHERE TABLE_SCHEMA          = 'deadstock_db'
  AND TABLE_NAME            = 'DEADSTOCK'
  AND COLUMN_NAME           = 'Branch_ID'
  AND REFERENCED_TABLE_NAME = 'BRANCH';


-- ADMIN Email column for OTP forgot-password flow

ALTER TABLE ADMIN ADD COLUMN IF NOT EXISTS Email VARCHAR(150) UNIQUE;
UPDATE ADMIN SET Email = 'admin@company.com' WHERE Username = 'admin' AND Email IS NULL;


-- One-head-one-branch / one-head-one-warehouse

ALTER TABLE BRANCH    ADD CONSTRAINT uq_branch_head    UNIQUE (Head_ID);
ALTER TABLE WAREHOUSE ADD CONSTRAINT uq_warehouse_head UNIQUE (Head_ID);


-- Verify everything:
SHOW CREATE TABLE DEADSTOCK;
DESCRIBE ADMIN;
SHOW INDEX FROM BRANCH;
SHOW INDEX FROM WAREHOUSE;

ALTER TABLE ADMIN
ADD COLUMN Email VARCHAR(150) UNIQUE;

UPDATE ADMIN
SET Email = 'shalakaparhad21@gmail.com',
    Password = 'nanuishu21'
WHERE Username = 'admin';

SELECT * FROM ADMIN;



-- warehouse_deadstock TABLE
-- Tracks deadstock received by warehouses

CREATE TABLE IF NOT EXISTS warehouse_deadstock (
    WD_ID         INT NOT NULL AUTO_INCREMENT,
    Warehouse_ID  INT NOT NULL,
    Deadstock_ID  INT NOT NULL,
    Quantity      INT NOT NULL DEFAULT 0,
    Received_At   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (WD_ID),

    FOREIGN KEY (Warehouse_ID)
        REFERENCES WAREHOUSE(Warehouse_ID)
        ON DELETE CASCADE,

    FOREIGN KEY (Deadstock_ID)
        REFERENCES DEADSTOCK(Deadstock_ID)
        ON DELETE CASCADE
);


-- SA_DEADSTOCK TABLE
-- Tracks deadstock received by Stock Allocation department

CREATE TABLE IF NOT EXISTS SA_DEADSTOCK (
    SA_DS_ID      INT NOT NULL AUTO_INCREMENT,
    Head_ID       INT NOT NULL,
    Deadstock_ID  INT NOT NULL,
    Quantity      INT NOT NULL DEFAULT 0,
    Received_At   TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    PRIMARY KEY (SA_DS_ID),

    FOREIGN KEY (Head_ID)
        REFERENCES HEAD(Head_ID)
        ON DELETE RESTRICT,

    FOREIGN KEY (Deadstock_ID)
        REFERENCES DEADSTOCK(Deadstock_ID)
        ON DELETE CASCADE
);


-- OPTIONAL INDEXES

CREATE INDEX idx_wd_deadstock
ON warehouse_deadstock(Deadstock_ID);

CREATE INDEX idx_sa_deadstock
ON SA_DEADSTOCK(Deadstock_ID);


-- SAMPLE DATA

INSERT INTO warehouse_deadstock
(Warehouse_ID, Deadstock_ID, Quantity)
VALUES
(1, 1, 120),
(1, 2, 80),
(2, 3, 60);

INSERT INTO SA_DEADSTOCK
(Head_ID, Deadstock_ID, Quantity)
VALUES
(6, 1, 120),
(6, 2, 80),
(6, 3, 60);


-- VERIFY

DESCRIBE warehouse_deadstock;
DESCRIBE SA_DEADSTOCK;

SELECT * FROM warehouse_deadstock;
SELECT * FROM SA_DEADSTOCK;


-- Add ON DELETE SET NULL for branch_id in Deadstock table
-- so that branch can be deleted even if it contains deadstock
-- by sending that deadstock in warehouse 
-- and archiving this branch in deleted-branch table

ALTER TABLE deadstock 
MODIFY Branch_ID INT NULL;

ALTER TABLE deadstock
DROP FOREIGN KEY deadstock_ibfk_1;

ALTER TABLE deadstock
ADD CONSTRAINT deadstock_ibfk_1
FOREIGN KEY (Branch_ID)
REFERENCES branch(Branch_ID)
ON DELETE SET NULL;