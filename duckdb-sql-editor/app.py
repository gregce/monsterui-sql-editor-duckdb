#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
DuckDB SQL Editor with FastHTML and MonsterUI
"""

import os
import json
import duckdb
import requests
import atexit
from pathlib import Path
from dotenv import load_dotenv
from fasthtml import serve
from fasthtml.common import *
from monsterui.all import *

# Load environment variables
load_dotenv()

# Define database path (relative to parent directory where analytics.duckdb is located)
DB_PATH = os.getenv("DUCKDB_PATH", "../duckdb-demo.duckdb")

# Global connection object
_db_connection = None

def get_connection():
    """Get a connection to the DuckDB database using a singleton pattern"""
    global _db_connection
    
    try:
        if _db_connection is None:
            db_path = Path(DB_PATH).resolve()
            if not db_path.exists():
                raise FileNotFoundError(f"Database file not found: {db_path}")
            
            # Connect to the database (read-only mode)
            print(f"Opening new database connection to {db_path} (singleton)")
            _db_connection = duckdb.connect(str(db_path), read_only=True)
        
        return _db_connection
    except Exception as e:
        print(f"Error connecting to database: {e}")
        raise

def reset_with_new_db(new_db_path):
    """Reset the connection with a new database file path"""
    global _db_connection, DB_PATH
    
    print(f"Changing database to: {new_db_path}")
    try:
        # Close existing connection if it exists
        if _db_connection is not None:
            try:
                _db_connection.close()
            except Exception as e:
                print(f"Error closing existing connection: {e}")
            finally:
                _db_connection = None
        
        # Update the global DB_PATH
        DB_PATH = new_db_path
        
        # Validate the new path
        db_path = Path(DB_PATH).resolve()
        if not db_path.exists():
            raise FileNotFoundError(f"Database file not found: {db_path}")
        
        # Create a new connection
        print(f"Creating new database connection to {db_path}")
        _db_connection = duckdb.connect(str(db_path), read_only=True)
        
        # Test the connection
        _db_connection.execute("SELECT 1").fetchall()
        print("Connection change successful")
        return True, None
    except Exception as e:
        error_msg = f"Failed to change database: {e}"
        print(error_msg)
        _db_connection = None
        return False, error_msg

def get_table_names():
    """Get a list of table names from the database"""
    conn = get_connection()
    try:
        # Query for all tables
        tables = conn.execute("SHOW TABLES").fetchall()
        return [table[0] for table in tables]
    except Exception as e:
        print(f"Error fetching table names: {e}")
        return []
    # Don't close the connection here anymore

def get_table_schema(table_name):
    """Get the schema for a specific table"""
    conn = get_connection()
    try:
        # Query for table schema
        print(f"Fetching schema for table: {table_name}")
        schema = conn.execute(f"DESCRIBE {table_name}").fetchall()
        print(f"Schema for {table_name}: {len(schema)} columns")
        return schema
    except Exception as e:
        print(f"Error fetching schema for table {table_name}: {e}")
        return []
    # Don't close the connection here anymore

def reset_connection():
    """Reset the database connection if it becomes unresponsive"""
    global _db_connection
    
    print("Resetting database connection...")
    try:
        if _db_connection is not None:
            try:
                _db_connection.close()
            except Exception as e:
                print(f"Error closing existing connection: {e}")
            finally:
                _db_connection = None
        
        # Create a new connection
        db_path = Path(DB_PATH).resolve()
        print(f"Creating new database connection to {db_path}")
        _db_connection = duckdb.connect(str(db_path), read_only=True)
        
        # Test the connection
        _db_connection.execute("SELECT 1").fetchall()
        print("Connection reset successful")
        return True
    except Exception as e:
        print(f"Failed to reset connection: {e}")
        _db_connection = None
        return False

def execute_query(query):
    """Execute a SQL query and return the results"""
    conn = get_connection()
    try:
        print(f"Executing query: {query[:100]}...")
        
        # Execute the query
        result = conn.execute(query).fetchall()
        # Get column names
        columns = []
        if conn.description is not None:
            columns = [col[0] for col in conn.description]
        print(f"Query executed successfully, returned {len(result)} rows")
        return {"columns": columns, "data": result}
    except Exception as e:
        print(f"Error executing query: {e}")
        
        # If there's a connection error, try to reset the connection
        if "connection" in str(e).lower() or "database" in str(e).lower():
            print("Connection issue detected, attempting to reset...")
            if reset_connection():
                # Retry the query once with the new connection
                try:
                    conn = get_connection()
                    print(f"Retrying query after connection reset...")
                    result = conn.execute(query).fetchall()
                    columns = []
                    if conn.description is not None:
                        columns = [col[0] for col in conn.description]
                    print(f"Retry successful, returned {len(result)} rows")
                    return {"columns": columns, "data": result}
                except Exception as retry_error:
                    print(f"Retry failed: {retry_error}")
                    return {"error": f"Query failed after connection reset: {retry_error}", 
                            "columns": [], "data": []}
        
        return {"error": str(e), "columns": [], "data": []}
    # Don't close the connection here anymore

# Initialize the app with MonsterUI theme
app, rt = fast_app(hdrs=Theme.blue.headers())

@rt('/')
def index():
    """Main page with SQL editor"""
    tables = get_table_names()
    print(f"Loaded {len(tables)} tables from database")
    
    # Pre-load schemas for all tables
    for table in tables:
        schema = get_table_schema(table)
        print(f"Pre-loaded schema for {table}: {len(schema)} columns")
    
    return Titled("", 
        # Add metadata for better styling
        Meta(name="viewport", content="width=device-width, initial-scale=1.0"),
        
        # Add a custom style for code highlighting and modern look
        Style("""
            body {
                min-height: 100vh;
                display: flex;
                flex-direction: column;
            }
            
            /* Modal styles */
            .modal-backdrop {
                position: fixed;
                top: 0;
                left: 0;
                width: 100%;
                height: 100%;
                background-color: rgba(0, 0, 0, 0.5);
                z-index: 9998;
                display: none;
            }
            
            .modal-container {
                position: fixed;
                top: 50%;
                left: 50%;
                transform: translate(-50%, -50%);
                background-color: white !important;
                border: 1px solid #ccc;
                padding: 0;
                border-radius: 8px;
                box-shadow: 0 4px 8px rgba(0, 0, 0, 0.1);
                z-index: 9999;
                width: 90%;
                max-width: 500px;
                max-height: 90vh;
                overflow-y: auto;
                display: none;
            }
            
            .modal-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 1rem;
                border-bottom: 1px solid #e5e7eb;
                background-color: #f9fafb;
                border-top-left-radius: 8px;
                border-top-right-radius: 8px;
            }
            
            .modal-body {
                padding: 1rem;
                background-color: white;
            }
            
            .modal-footer {
                padding: 1rem;
                border-top: 1px solid #e5e7eb;
                display: flex;
                justify-content: flex-end;
                background-color: #f9fafb;
                border-bottom-left-radius: 8px;
                border-bottom-right-radius: 8px;
            }
            
            .separator {
                margin: 2rem 0;
                text-align: center;
                position: relative;
            }
            
            .separator::before,
            .separator::after {
                content: '';
                position: absolute;
                top: 50%;
                width: 40%;
                height: 1px;
                background-color: #e5e7eb;
            }
            
            .separator::before {
                left: 0;
            }
            
            .separator::after {
                right: 0;
            }
            
            .separator-text {
                display: inline-block;
                position: relative;
                padding: 0 1rem;
                background-color: white;
                color: #6b7280;
            }
            
            /* Additional styles for the database modal */
            #database-modal {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                display: flex;
                align-items: center;
                justify-content: center;
                z-index: 50;
            }
            
            #database-modal.hidden {
                display: none;
            }
            
            #database-modal > div {
                background-color: white;
                box-shadow: 0 10px 25px rgba(0, 0, 0, 0.3);
                border-radius: 0.5rem;
                width: 100%;
                max-width: 500px;
                max-height: 90vh;
                overflow-y: auto;
                margin: 2rem;
            }
            
            #modal-backdrop {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: rgba(0, 0, 0, 0.5);
                z-index: 40;
            }
            
            #modal-backdrop.hidden {
                display: none;
            }
            
            #database-modal .form-group {
                margin-bottom: 1rem;
            }
            main {
                flex: 1;
            }
            .footer {
                margin-top: auto;
                padding: 1rem 0;
                background-color: white;
                border-top: 1px solid #e5e7eb;
                width: 100%;
            }
            .container {
                display: flex;
                flex-direction: column;
                min-height: 100vh;
            }
            .sql-editor {
                font-family: 'Monaco', 'Menlo', 'Ubuntu Mono', 'Consolas', monospace;
                line-height: 1.5;
                tab-size: 4;
                background-color: #f8f9fc;
                border: none; /* Remove border as it's on the wrapper now */
                max-height: 500px;
                overflow-y: auto;
                white-space: pre;
                width: 100%;
                transition: all 0.2s ease-in-out;
                position: relative;
            }
            .sql-editor:focus {
                outline: none;
                box-shadow: none; /* Remove box shadow as focus styling will be on wrapper */
            }
            form.nl-mode .sql-editor {
                background-color: #f0f9ff;
                transition: all 0.2s ease-in-out;
                box-shadow: none;
            }
            form.nl-mode .editor-wrapper:focus-within {
                box-shadow: 0 0 0 3px rgba(59, 130, 246, 0.3), 0 0 8px rgba(59, 130, 246, 0.15) inset;
                border-color: #3b82f6;
            }
            .query-container {
                display: flex;
                flex-direction: column;
                position: relative;
                border-radius: 0.375rem;
                overflow: hidden;
                margin-bottom: 1rem;
                box-shadow: 0 0 0 1px rgba(0, 0, 0, 0.05);
            }
            
            /* Create a wrapper for the editor to ensure proper positioning context */
            .editor-wrapper {
                position: relative;
                width: 100%;
                border-radius: 0.375rem;
                overflow: hidden;
                border: 1px solid #e2e8f0;
            }
            
            form.nl-mode .editor-wrapper {
                border-color: #93c5fd;
                box-shadow: 0 0 8px rgba(59, 130, 246, 0.15) inset;
            }
            
            .line-numbers {
                position: absolute;
                left: 0;
                top: 0;
                bottom: 0;
                width: 40px;
                background-color: #f1f5f9;
                border-right: 1px solid #e2e8f0;
                color: #64748b;
                font-family: monospace;
                font-size: 0.875rem;
                padding-top: 0.75rem;
                padding-right: 8px;
                text-align: right;
                user-select: none;
                z-index: 1;
                transition: all 0.2s ease-in-out;
                overflow: hidden;
            }
            
            form.nl-mode .line-numbers {
                background-color: #e0f2fe;
                border-color: #bae6fd;
                transition: all 0.2s ease-in-out;
            }
            
            .with-line-numbers {
                padding-left: 50px !important;
            }
            .table-item {
                border-left: 3px solid transparent;
                transition: all 0.2s;
            }
            .table-item:hover {
                border-left-color: #3b82f6;
                background-color: #eff6ff;
            }
            .table-item.active {
                border-left-color: #3b82f6;
                background-color: #eff6ff;
            }
            .table-list {
                border-radius: 0.375rem;
                overflow: hidden;
            }
            .result-container {
                box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
                border-radius: 0.375rem;
                overflow: hidden;
                margin-top: 0;
                max-height: 700px;
                overflow-y: auto;
            }
            .result-table th {
                background-color: #f1f5f9;
                position: sticky;
                top: 0;
                z-index: 10;
                font-weight: 600;
            }
            .result-table {
                width: 100%;
                table-layout: auto;
            }
            .table-wrapper {
                width: 100%;
                overflow-x: auto;
                padding-bottom: 8px;
            }
            .header-actions {
                display: flex;
                align-items: center;
                gap: 8px;
            }
            .schema-container {
                max-height: 0;
                overflow: hidden;
                transition: max-height 0.3s ease-out, opacity 0.2s ease-out;
                opacity: 0;
                margin-left: 12px;
                margin-right: 12px;
                border-left: 2px solid #e5e7eb;
            }
            .schema-container.open {
                max-height: 500px;
                opacity: 1;
                padding-left: 10px;
                margin-top: 5px;
                margin-bottom: 10px;
            }
            .query-history-item {
                cursor: pointer;
                transition: all 0.2s;
            }
            .query-history-item:hover {
                background-color: #f3f4f6;
            }
            .sidebar {
                width: 280px;
                min-width: 280px;
                height: 500px;
                max-height: 500px;
                overflow-y: hidden;
                display: flex;
                flex-direction: column;
            }
            .main-content {
                flex: 1;
                min-width: 0;
                width: 100%;
                overflow: hidden;
                display: flex;
                flex-direction: column;
            }
            .schema-table {
                overflow-x: auto;
                width: 100%;
                max-height: 300px;
                border: 1px solid #e5e7eb;
                margin-top: 8px;
                border-radius: 4px;
            }
            .schema-table table {
                min-width: 100%;
                border-collapse: separate;
                border-spacing: 0;
            }
            .schema-table th {
                position: sticky;
                top: 0;
                background-color: #f1f5f9;
                z-index: 1;
                padding: 6px;
                text-align: left;
                font-weight: 600;
                border-bottom: 1px solid #e5e7eb;
            }
            .schema-table td {
                padding: 4px 6px;
                border-bottom: 1px solid #e5e7eb;
                font-size: 0.75rem;
            }
            .table-row:hover {
                background-color: #f3f4f6;
            }
            .table-header {
                padding: 10px 12px;
                cursor: pointer;
                display: flex;
                justify-content: space-between;
                align-items: center;
                border-radius: 4px;
                transition: all 0.2s;
                position: relative;
            }
            .table-header:hover {
                background-color: #f3f4f6;
            }
            .table-header.active {
                background-color: #ebf5ff;
            }
            .toggle-indicator {
                display: inline-block;
                width: 20px;
                height: 20px;
                text-align: center;
                line-height: 20px;
                font-weight: bold;
                color: #3b82f6;
                transition: transform 0.2s ease;
                transform-origin: center;
                position: absolute;
                right: 12px;
            }
            .toggle-indicator.open {
                transform: rotate(90deg);
            }
            .schema-section {
                flex: 1;
                overflow-y: auto;
                border: 1px solid #e5e7eb;
                border-radius: 0.375rem;
                max-height: calc(500px - 50px);
            }
            .schema-column-list {
                list-style: none;
                padding: 0;
                margin: 0;
            }
            .schema-column-item {
                display: flex;
                padding: 4px 8px;
                border-bottom: 1px solid #f3f4f6;
                font-size: 0.75rem;
                align-items: center;
            }
            .schema-column-item:last-child {
                border-bottom: none;
            }
            .schema-column-item:hover {
                background-color: #f9fafb;
            }
            .column-name {
                font-weight: 500;
                flex: 2;
                color: #4b5563;
            }
            .column-type {
                flex: 2;
                font-family: monospace;
                color: #6b7280;
                font-size: 0.7rem;
            }
            .column-nullable {
                flex: 1;
                text-align: center;
            }
            .schema-summary {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 4px 8px;
                background-color: #f9fafb;
                border-radius: 4px;
                margin-top: 6px;
                margin-bottom: 8px;
                font-size: 0.7rem;
                color: #6b7280;
            }
            .schema-header {
                font-weight: 600;
                font-size: 0.8rem;
                color: #374151;
                margin-bottom: 6px;
                padding-bottom: 3px;
                border-bottom: 1px solid #e5e7eb;
            }
            .schema-actions {
                margin-bottom: 8px;
                display: flex;
                justify-content: space-between;
                align-items: center;
            }
            .schema-actions button {
                font-size: 0.75rem;
                padding: 4px 8px;
            }
            .column-count {
                font-size: 0.7rem;
                background-color: #e5e7eb;
                color: #4b5563;
                padding: 2px 6px;
                border-radius: 10px;
                margin-left: 5px;
            }
            .main-layout {
                display: flex;
                flex-direction: column;
                gap: 16px;
            }
            .editor-row {
                display: flex;
                gap: 16px;
            }
            .results-row {
                width: 100%;
                margin-top: 8px;
            }
            @media (max-width: 768px) {
                .main-layout {
                    flex-direction: column;
                }
                .sidebar {
                    width: 100%;
                }
            }
            .history-container {
                margin-top: 16px;
                width: 100%;
            }
            .sidebar-section {
                margin-bottom: 16px;
            }
            .sidebar-section-heading {
                font-weight: 600;
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 8px 12px;
                background-color: #f9fafb;
                border-bottom: 1px solid #e5e7eb;
            }
            /* JSON related styles */
            .json-cell {
                position: relative;
                cursor: pointer;
            }
            .json-cell:hover {
                background-color: #f0f9ff;
            }
            .json-badge {
                font-size: 0.65rem;
                background-color: #3b82f6;
                color: white;
                padding: 1px 4px;
                border-radius: 4px;
                margin-left: 4px;
                vertical-align: middle;
            }
            .json-prettified {
                white-space: pre-wrap;
                font-family: monospace;
                font-size: 0.75rem;
                max-height: 200px;
                overflow-y: auto;
                padding: 0.5rem;
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 0.25rem;
                margin-top: 0.25rem;
            }
            .json-preview-container {
                position: relative;
            }
            .json-explorer-modal {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: rgba(0, 0, 0, 0.5);
                z-index: 1000;
                display: flex;
                justify-content: center;
                align-items: center;
            }
            .json-explorer-content {
                background-color: white;
                width: 90%;
                max-width: 1000px;
                height: 90%;
                border-radius: 0.5rem;
                box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1);
                display: flex;
                flex-direction: column;
            }
            .json-explorer-header {
                display: flex;
                justify-content: space-between;
                align-items: center;
                padding: 1rem;
                border-bottom: 1px solid #e2e8f0;
            }
            .json-explorer-body {
                flex: 1;
                display: flex;
                overflow: hidden;
            }
            .json-tree {
                width: 30%;
                overflow-y: auto;
                border-right: 1px solid #e2e8f0;
                padding: 1rem;
            }
            .json-content {
                flex: 1;
                overflow-y: auto;
                padding: 1rem;
                white-space: pre-wrap;
                font-family: monospace;
            }
            .json-path {
                padding: 0.5rem 1rem;
                background-color: #f1f5f9;
                font-family: monospace;
                font-size: 0.875rem;
                margin-bottom: 1rem;
                border-radius: 0.25rem;
                border: 1px solid #e2e8f0;
            }
            .json-tree-item {
                margin: 0.25rem 0;
                cursor: pointer;
                padding: 0.25rem 0.5rem;
                border-radius: 0.25rem;
                transition: all 0.2s;
            }
            .json-tree-item:hover {
                background-color: #f1f5f9;
            }
            .json-tree-item.active {
                background-color: #e0f2fe;
                font-weight: 600;
            }
            .json-tree-toggle {
                cursor: pointer;
                user-select: none;
                margin-right: 0.25rem;
            }
            .json-tree-children {
                padding-left: 1.5rem;
            }
            .json-value-type {
                font-size: 0.7rem;
                color: #64748b;
                margin-left: 0.5rem;
            }
            .json-key {
                color: #0369a1;
            }
            .json-copy-btn {
                position: absolute;
                top: 0.5rem;
                right: 0.5rem;
                padding: 0.25rem 0.5rem;
                font-size: 0.75rem;
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 0.25rem;
                cursor: pointer;
            }
            .json-copy-btn:hover {
                background-color: #e0f2fe;
            }
            .close-modal-btn {
                cursor: pointer;
                padding: 0.5rem;
                border-radius: 0.25rem;
                background-color: #f1f5f9;
                border: none;
            }
            .close-modal-btn:hover {
                background-color: #e2e8f0;
            }
            /* Tabs styling for query history */
            .query-tabs {
                display: flex;
                overflow-x: auto;
                border-bottom: 1px solid #e5e7eb;
                margin-bottom: 0;
                background-color: #f9fafb;
                border-top-left-radius: 0.375rem;
                border-top-right-radius: 0.375rem;
                padding-left: 0.5rem;
                padding-right: 0.5rem;
                -webkit-overflow-scrolling: touch;
                scrollbar-width: thin;
                scrollbar-color: #cbd5e1 #f1f5f9;
            }
            .query-tabs::-webkit-scrollbar {
                height: 6px;
            }
            .query-tabs::-webkit-scrollbar-track {
                background: #f1f5f9;
            }
            .query-tabs::-webkit-scrollbar-thumb {
                background-color: #cbd5e1;
                border-radius: 3px;
            }
            .query-tab {
                padding: 0.75rem 1rem;
                white-space: nowrap;
                cursor: pointer;
                border-bottom: 2px solid transparent;
                transition: all 0.2s;
                font-size: 0.875rem;
                display: flex;
                align-items: center;
                gap: 0.5rem;
                position: relative;
            }
            .query-tab:hover {
                background-color: #f3f4f6;
            }
            .query-tab.active {
                border-bottom-color: #3b82f6;
                background-color: #eff6ff;
                font-weight: 500;
                color: #1e40af;
                z-index: 1;
            }
            .query-tab-time {
                font-size: 0.7rem;
                color: #6b7280;
            }
            .query-tab-close {
                width: 18px;
                height: 18px;
                border-radius: 50%;
                display: inline-flex;
                align-items: center;
                justify-content: center;
                font-size: 0.7rem;
                background-color: #e5e7eb;
                color: #4b5563;
                margin-left: 0.25rem;
                visibility: hidden;
            }
            .query-tab:hover .query-tab-close {
                visibility: visible;
            }
            .query-tab-close:hover {
                background-color: #ef4444;
                color: white;
            }
            .query-tab.active::after {
                content: '';
                position: absolute;
                bottom: -1px;
                left: 0;
                right: 0;
                height: 2px;
                background-color: #3b82f6;
            }
            .new-tab-btn {
                padding: 0.5rem 0.75rem;
                color: #6b7280;
                background-color: transparent;
                border: none;
                cursor: pointer;
                font-size: 0.75rem;
                display: flex;
                align-items: center;
                gap: 0.25rem;
            }
            .new-tab-btn:hover {
                background-color: #f3f4f6;
                color: #3b82f6;
            }
            /* Result styling to ensure proper isolation */
            .query-content {
                display: none;
            }
            .single-query-result {
                margin-top: 0;
                padding-top: 0.5rem;
                overflow: hidden;
            }
            .query-result-panel {
                overflow-y: auto;
                max-height: 600px;
            }
            /* Mode toggle switch styles */
            .switch {
                position: relative;
                display: inline-block;
                width: 60px;
                height: 24px;
            }
            .switch input {
                opacity: 0;
                width: 0;
                height: 0;
            }
            .slider {
                position: absolute;
                cursor: pointer;
                top: 0;
                left: 0;
                right: 0;
                bottom: 0;
                background-color: #ccc;
                transition: .4s;
                border-radius: 34px;
            }
            .slider:before {
                position: absolute;
                content: "";
                height: 18px;
                width: 18px;
                left: 4px;
                bottom: 3px;
                background-color: white;
                transition: .4s;
                border-radius: 50%;
            }
            input:checked + .slider {
                background-color: #3b82f6;
            }
            input:focus + .slider {
                box-shadow: 0 0 1px #3b82f6;
            }
            input:checked + .slider:before {
                transform: translateX(34px);
            }
            .mode-toggle-container {
                display: flex;
                align-items: center;
                gap: 8px;
                margin-bottom: 10px;
                padding: 8px;
                background-color: #f9fafb;
                border-radius: 6px;
                border: 1px solid #e5e7eb;
                transition: all 0.2s ease-in-out;
            }
            form.nl-mode ~ .mode-toggle-container {
                background-color: #f0f7ff;
                border-color: #bfdbfe;
            }
            .mode-label {
                font-size: 0.875rem;
                font-weight: 500;
                transition: color 0.2s ease-in-out;
            }
            .mode-label.active {
                color: #3b82f6;
            }
            /* Add a badge for NL mode */
            .nl-badge {
                display: none;
                background-color: #3b82f6;
                color: white;
                padding: 2px 6px;
                border-radius: 4px;
                font-size: 0.7rem;
                font-weight: 500;
                margin-left: 8px;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
                animation: fadeIn 0.3s ease-in-out;
            }
            form.nl-mode ~ .nl-badge, 
            .nl-mode .nl-badge {
                display: inline-block;
            }
            @keyframes fadeIn {
                from { opacity: 0; }
                to { opacity: 1; }
            }
            /* Styles for the NL translate button */
            .translate-btn {
                background-color: #3b82f6;
                color: white;
                border: none;
                padding: 8px 16px;
                border-radius: 6px;
                font-weight: 500;
                cursor: pointer;
                transition: all 0.2s ease-in-out;
                display: none;
                box-shadow: 0 1px 2px rgba(0, 0, 0, 0.1);
            }
            .translate-btn:hover {
                background-color: #2563eb;
                box-shadow: 0 2px 4px rgba(0, 0, 0, 0.15);
                transform: translateY(-1px);
            }
            form.nl-mode .translate-btn {
                display: inline-block;
                animation: fadeIn 0.3s ease-in-out;
            }
            form.nl-mode .execute-btn {
                display: none;
            }
            .nl-hint {
                display: none;
                font-size: 0.75rem;
                color: #6b7280;
                margin-top: 4px;
                padding: 4px 0;
                text-align: center;
                transition: all 0.2s ease-in-out;
            }
            form.nl-mode .nl-hint {
                display: block;
                color: #3b82f6;
                animation: fadeIn 0.3s ease-in-out;
            }
        """),
        
        # Add script for expanded functionality
        Script("""
            // Line number functionality
            function updateLineNumbers() {
                const editor = document.getElementById('sql-query');
                const lineNumbers = document.getElementById('line-numbers');
                if (!editor || !lineNumbers) return;
                
                const lines = editor.value.split('\\n');
                let lineNumbersText = '';
                
                for (let i = 1; i <= lines.length; i++) {
                    lineNumbersText += i + '\\n';
                }
                
                lineNumbers.textContent = lineNumbersText;
                
                // Ensure line numbers have the same height as the editor content
                lineNumbers.style.height = editor.scrollHeight + 'px';
            }
            
            // Clear editor and results
            function clearEditor() {
                // Clear the SQL query field
                const editor = document.getElementById('sql-query');
                if (editor) {
                    editor.value = '';
                    updateLineNumbers();
                }
                
                // Clear the results panel
                const resultsPanel = document.getElementById('query-results');
                if (resultsPanel) {
                    resultsPanel.innerHTML = '<div class="p-4 text-center text-gray-500">Results cleared. Execute a query to see results.</div>';
                }
                
                console.log('Editor and results cleared');
            }
            
            // Enhanced table schema toggle
            function toggleSchema(tableId) {
                console.log('Toggling schema for table:', tableId);
                const schemaContainer = document.getElementById(`schema-${tableId}`);
                const tableHeader = document.getElementById(`table-header-${tableId}`);
                const toggleIndicator = document.getElementById(`toggle-${tableId}`);
                
                if (!schemaContainer || !tableHeader) {
                    console.error('Schema container or table header not found');
                    return;
                }
                
                // Toggle active class and open state
                const isOpen = tableHeader.classList.contains('active');
                
                // Close all schemas first
                document.querySelectorAll('.schema-container').forEach(container => {
                    container.classList.remove('open');
                });
                document.querySelectorAll('.table-header').forEach(header => {
                    header.classList.remove('active');
                });
                document.querySelectorAll('.toggle-indicator').forEach(indicator => {
                    indicator.classList.remove('open');
                });
                
                // Toggle this schema if it wasn't the one that was open
                if (!isOpen) {
                    tableHeader.classList.add('active');
                    schemaContainer.classList.add('open');
                    toggleIndicator.classList.add('open');
                    console.log(`Opening schema for ${tableId}`);
                } else {
                    console.log(`Closing schema for ${tableId}`);
                }
            }
            
            // Add query to history
            function addQueryToHistory(query, timestamp) {
                // Create a unique ID for this query tab
                const tabId = 'query-tab-' + Date.now();
                const contentId = 'query-content-' + Date.now();
                
                // Get tabs container
                const tabsContainer = document.getElementById('query-tabs');
                if (!tabsContainer) {
                    console.error('Query tabs container not found');
                    return;
                }
                
                // Hide "no queries" message if shown
                const noQueriesMessage = document.getElementById('no-queries-message');
                if (noQueriesMessage) {
                    noQueriesMessage.style.display = 'none';
                }
                
                // Format the query (truncate if too long)
                const queryText = query.length > 30 ? query.substring(0, 27) + '...' : query;
                
                // Create new tab
                const newTab = document.createElement('div');
                newTab.className = 'query-tab';
                newTab.id = tabId;
                newTab.innerHTML = `
                    <span class="query-tab-text">${queryText}</span>
                    <span class="query-tab-time">${timestamp}</span>
                    <span class="query-tab-close" onclick="removeQueryTab('${tabId}', '${contentId}', event)">×</span>
                `;
                
                // Store query content in a data attribute
                newTab.setAttribute('data-query', query);
                
                // Add click handler to activate this tab
                newTab.addEventListener('click', function(e) {
                    if (e.target.classList.contains('query-tab-close')) {
                        return; // Don't activate when clicking the close button
                    }
                    
                    activateQueryTab(tabId, contentId, query);
                });
                
                // Add to beginning of tabs
                if (tabsContainer.children.length > 0) {
                    tabsContainer.insertBefore(newTab, tabsContainer.children[0]);
                } else {
                    tabsContainer.appendChild(newTab);
                }
                
                // Store the current results in a hidden div
                const resultsPanel = document.getElementById('query-results');
                if (resultsPanel) {
                    // Create a content container for this tab if it doesn't exist
                    let contentContainer = document.getElementById(contentId);
                    if (!contentContainer) {
                        contentContainer = document.createElement('div');
                        contentContainer.id = contentId;
                        contentContainer.className = 'query-content';
                        contentContainer.style.display = 'none';
                        
                        // Add this content container to a hidden container in the body
                        let hiddenContainer = document.getElementById('hidden-results-container');
                        if (!hiddenContainer) {
                            hiddenContainer = document.createElement('div');
                            hiddenContainer.id = 'hidden-results-container';
                            hiddenContainer.style.display = 'none';
                            document.body.appendChild(hiddenContainer);
                        }
                        hiddenContainer.appendChild(contentContainer);
                    }
                    
                    // Copy current results to this container
                    contentContainer.innerHTML = resultsPanel.innerHTML;
                    console.log('Saved results for tab', tabId, 'content size:', contentContainer.innerHTML.length);
                }
                
                // Activate this tab
                activateQueryTab(tabId, contentId, query);
                
                // Limit to 10 tabs
                const tabs = tabsContainer.querySelectorAll('.query-tab');
                if (tabs.length > 10) {
                    // Find the oldest tab (last one) and its content, and remove both
                    const oldestTab = tabs[tabs.length - 1];
                    const oldestContentId = 'query-content-' + oldestTab.id.replace('query-tab-', '');
                    const oldestContent = document.getElementById(oldestContentId);
                    
                    if (oldestContent) {
                        oldestContent.parentNode.removeChild(oldestContent);
                    }
                    oldestTab.parentNode.removeChild(oldestTab);
                }
            }
            
            // Activate a query tab
            function activateQueryTab(tabId, contentId, query) {
                console.log('Activating tab:', tabId, 'with content:', contentId);
                
                // Deactivate all tabs
                document.querySelectorAll('.query-tab').forEach(tab => {
                    tab.classList.remove('active');
                });
                
                // Activate this tab
                const tab = document.getElementById(tabId);
                if (tab) {
                    tab.classList.add('active');
                }
                
                // First update the SQL editor with this query
                const editor = document.getElementById('sql-query');
                if (editor) {
                    editor.value = query;
                    updateLineNumbers();
                }
                
                // Get the content and results panel
                const content = document.getElementById(contentId);
                const resultsPanel = document.getElementById('query-results');
                
                if (content && resultsPanel) {
                    console.log('Found content and results panel, updating content');
                    // Clear out existing results first
                    resultsPanel.innerHTML = '';
                    // Then replace with the content for this tab
                    resultsPanel.innerHTML = content.innerHTML;
                } else {
                    console.error('Missing content or results panel', contentId, resultsPanel);
                    // If we're missing content, show a message
                    if (resultsPanel) {
                        resultsPanel.innerHTML = '<div class="p-4 text-center text-gray-500">Results not available. Execute the query again to see results.</div>';
                    }
                }
            }
            
            // Remove a query tab
            function removeQueryTab(tabId, contentId, event) {
                // Stop event propagation to prevent tab activation
                event.stopPropagation();
                
                // Remove the tab
                const tab = document.getElementById(tabId);
                if (tab) {
                    // Check if it's the active tab
                    const isActive = tab.classList.contains('active');
                    
                    // Get parent to check if there are other tabs
                    const tabsContainer = tab.parentNode;
                    
                    // Remove the tab
                    tab.parentNode.removeChild(tab);
                    
                    // Remove the content
                    const content = document.getElementById(contentId);
                    if (content) {
                        content.parentNode.removeChild(content);
                    }
                    
                    // If there are other tabs and this was the active one, activate the first one
                    if (isActive && tabsContainer.children.length > 0) {
                        // Find first actual tab (not the new tab button)
                        const firstTab = tabsContainer.querySelector('.query-tab');
                        if (firstTab) {
                            const firstTabId = firstTab.id;
                            const firstContentId = 'query-content-' + firstTabId.replace('query-tab-', '');
                            const query = firstTab.getAttribute('data-query') || '';
                            activateQueryTab(firstTabId, firstContentId, query);
                        }
                    } else if (tabsContainer.children.length === 0) {
                        // If no tabs left, show no queries message
                        const noQueriesMessage = document.getElementById('no-queries-message');
                        if (noQueriesMessage) {
                            noQueriesMessage.style.display = 'block';
                        }
                        
                        // Clear results panel
                        const resultsPanel = document.getElementById('query-results');
                        if (resultsPanel) {
                            resultsPanel.innerHTML = '<div class="p-4 text-center text-gray-500">No query results to display. Execute a query to see results.</div>';
                        }
                    }
                }
            }
            
            // Clear tab history
            function clearQueryHistory() {
                const tabsContainer = document.getElementById('query-tabs');
                if (tabsContainer) {
                    // Remove all tabs
                    const tabs = tabsContainer.querySelectorAll('.query-tab');
                    tabs.forEach(tab => {
                        const contentId = 'query-content-' + tab.id.replace('query-tab-', '');
                        const content = document.getElementById(contentId);
                        if (content) {
                            content.parentNode.removeChild(content);
                        }
                        tab.parentNode.removeChild(tab);
                    });
                    
                    // Show no queries message
                    const noQueriesMessage = document.getElementById('no-queries-message');
                    if (noQueriesMessage) {
                        noQueriesMessage.style.display = 'block';
                    }
                    
                    // Clear results panel
                    const resultsPanel = document.getElementById('query-results');
                    if (resultsPanel) {
                        resultsPanel.innerHTML = '<div class="p-4 text-center text-gray-500">No query results to display. Execute a query to see results.</div>';
                    }
                }
            }
            
            // Check if a string is JSON
            function isJsonString(str) {
                if (typeof str !== 'string') return false;
                
                // Quick check for JSON-like structure
                if (!(str.startsWith('{') && str.endsWith('}')) && 
                    !(str.startsWith('[') && str.endsWith(']'))) {
                    return false;
                }
                
                try {
                    JSON.parse(str);
                    return true;
                } catch (e) {
                    return false;
                }
            }
            
            // Format JSON for display
            function formatJsonForDisplay(jsonString, indent = 2) {
                try {
                    const parsedJson = JSON.parse(jsonString);
                    return JSON.stringify(parsedJson, null, indent);
                } catch (e) {
                    console.error('Error formatting JSON:', e);
                    return jsonString;
                }
            }
            
            // Toggle JSON prettification
            function toggleJsonPrettify(element) {
                const jsonCell = element.closest('.json-cell');
                const jsonData = jsonCell.getAttribute('data-json');
                const prettifiedContainer = jsonCell.querySelector('.json-prettified');
                
                if (prettifiedContainer.style.display === 'none' || !prettifiedContainer.style.display) {
                    prettifiedContainer.textContent = formatJsonForDisplay(jsonData);
                    prettifiedContainer.style.display = 'block';
                } else {
                    prettifiedContainer.style.display = 'none';
                }
            }
            
            // Open JSON explorer modal
            function openJsonExplorer(jsonString, columnName) {
                try {
                    // Parse the JSON
                    const jsonData = JSON.parse(jsonString);
                    
                    // Create modal
                    const modal = document.createElement('div');
                    modal.className = 'json-explorer-modal';
                    modal.id = 'json-explorer-modal';
                    
                    // Create modal content
                    modal.innerHTML = `
                        <div class="json-explorer-content">
                            <div class="json-explorer-header">
                                <h3 class="text-lg font-semibold">JSON Explorer: ${columnName}</h3>
                                <button class="close-modal-btn" onclick="closeJsonExplorer()">×</button>
                            </div>
                            <div class="json-path" id="current-json-path">$</div>
                            <div class="json-explorer-body">
                                <div class="json-tree" id="json-tree"></div>
                                <div class="json-content" id="json-content">${formatJsonForDisplay(jsonString)}</div>
                            </div>
                        </div>
                    `;
                    
                    // Add to document
                    document.body.appendChild(modal);
                    
                    // Generate tree
                    generateJsonTree(jsonData, document.getElementById('json-tree'), '$');
                    
                } catch (e) {
                    console.error('Error opening JSON explorer:', e);
                    alert('Error parsing JSON data');
                }
            }
            
            // Close JSON explorer modal
            function closeJsonExplorer() {
                const modal = document.getElementById('json-explorer-modal');
                if (modal) {
                    document.body.removeChild(modal);
                }
            }
            
            // Generate JSON tree
            function generateJsonTree(data, container, path = '$') {
                if (Array.isArray(data)) {
                    // Handle array
                    const list = document.createElement('div');
                    list.className = 'json-tree-children';
                    
                    for (let i = 0; i < data.length; i++) {
                        const itemPath = `${path}[${i}]`;
                        const item = document.createElement('div');
                        item.className = 'json-tree-item';
                        
                        const valueType = typeof data[i];
                        const isComplex = valueType === 'object' && data[i] !== null;
                        
                        if (isComplex) {
                            const toggle = document.createElement('span');
                            toggle.className = 'json-tree-toggle';
                            toggle.textContent = '▶';
                            toggle.onclick = function(e) {
                                e.stopPropagation();
                                const childContainer = this.parentNode.querySelector('.json-tree-children');
                                if (childContainer.style.display === 'none') {
                                    childContainer.style.display = 'block';
                                    this.textContent = '▼';
                                } else {
                                    childContainer.style.display = 'none';
                                    this.textContent = '▶';
                                }
                            };
                            item.appendChild(toggle);
                        }
                        
                        const itemText = document.createElement('span');
                        itemText.innerHTML = `[${i}]<span class="json-value-type">${valueType}</span>`;
                        item.appendChild(itemText);
                        
                        item.onclick = function(e) {
                            e.stopPropagation();
                            document.querySelectorAll('.json-tree-item').forEach(el => el.classList.remove('active'));
                            this.classList.add('active');
                            document.getElementById('current-json-path').textContent = itemPath;
                            if (!isComplex) {
                                document.getElementById('json-content').textContent = JSON.stringify(data[i], null, 2);
                            } else {
                                document.getElementById('json-content').textContent = JSON.stringify(data[i], null, 2);
                            }
                        };
                        
                        if (isComplex) {
                            const childContainer = document.createElement('div');
                            childContainer.className = 'json-tree-children';
                            childContainer.style.display = 'none';
                            generateJsonTree(data[i], childContainer, itemPath);
                            item.appendChild(childContainer);
                        }
                        
                        list.appendChild(item);
                    }
                    
                    container.appendChild(list);
                } else if (typeof data === 'object' && data !== null) {
                    // Handle object
                    const list = document.createElement('div');
                    list.className = 'json-tree-children';
                    
                    for (const key in data) {
                        const itemPath = path === '$' ? `$.${key}` : `${path}.${key}`;
                        const item = document.createElement('div');
                        item.className = 'json-tree-item';
                        
                        const valueType = typeof data[key];
                        const isComplex = valueType === 'object' && data[key] !== null;
                        
                        if (isComplex) {
                            const toggle = document.createElement('span');
                            toggle.className = 'json-tree-toggle';
                            toggle.textContent = '▶';
                            toggle.onclick = function(e) {
                                e.stopPropagation();
                                const childContainer = this.parentNode.querySelector('.json-tree-children');
                                if (childContainer.style.display === 'none') {
                                    childContainer.style.display = 'block';
                                    this.textContent = '▼';
                                } else {
                                    childContainer.style.display = 'none';
                                    this.textContent = '▶';
                                }
                            };
                            item.appendChild(toggle);
                        }
                        
                        const itemText = document.createElement('span');
                        itemText.innerHTML = `<span class="json-key">${key}</span><span class="json-value-type">${valueType}</span>`;
                        item.appendChild(itemText);
                        
                        item.onclick = function(e) {
                            e.stopPropagation();
                            document.querySelectorAll('.json-tree-item').forEach(el => el.classList.remove('active'));
                            this.classList.add('active');
                            document.getElementById('current-json-path').textContent = itemPath;
                            if (!isComplex) {
                                document.getElementById('json-content').textContent = JSON.stringify(data[key], null, 2);
                            } else {
                                document.getElementById('json-content').textContent = JSON.stringify(data[key], null, 2);
                            }
                        };
                        
                        if (isComplex) {
                            const childContainer = document.createElement('div');
                            childContainer.className = 'json-tree-children';
                            childContainer.style.display = 'none';
                            generateJsonTree(data[key], childContainer, itemPath);
                            item.appendChild(childContainer);
                        }
                        
                        list.appendChild(item);
                    }
                    
                    container.appendChild(list);
                }
            }
            
            // Copy JSON path to clipboard
            function copyJsonPath() {
                const path = document.getElementById('current-json-path').textContent;
                navigator.clipboard.writeText(path).then(() => {
                    alert('JSON path copied to clipboard!');
                }).catch(err => {
                    console.error('Failed to copy:', err);
                });
            }
            
            // Initialize on page load
            document.addEventListener('DOMContentLoaded', function() {
                const editor = document.getElementById('sql-query');
                if (editor) {
                    editor.addEventListener('input', updateLineNumbers);
                    editor.addEventListener('scroll', function() {
                        const lineNumbers = document.getElementById('line-numbers');
                        if (lineNumbers) {
                            lineNumbers.scrollTop = editor.scrollTop;
                        }
                    });
                    
                    // Initialize line numbers
                    updateLineNumbers();
                    
                    // Also handle window resize which might affect editor size
                    window.addEventListener('resize', updateLineNumbers);
                }
                
                // Initialize mode toggle
                toggleQueryMode();
                
                // Log for debugging
                console.log('DOMContentLoaded event fired, initializing SQL editor');
            });
            
            // Fallback form submission handler
            document.addEventListener('DOMContentLoaded', function() {
                console.log('Setting up fallback form handler');
                setupFallbackFormHandler();
            });
            
            function setupFallbackFormHandler() {
                // Add a fallback vanilla JS form handler in case HTMX doesn't work
                const form = document.getElementById('sql-query-form');
                if (form) {
                    console.log('Found form, adding fallback handler');
                    
                    form.addEventListener('submit', function(e) {
                        console.log('Form submit intercepted by fallback handler');
                        
                        // Only intercept if we suspect HTMX isn't working
                        const htmxWorking = typeof htmx !== 'undefined' && 
                                           form.hasAttribute('hx-post') &&
                                           document.querySelector('#sql-query-form[hx-post]');
                                           
                        if (!htmxWorking) {
                            console.log('Using fallback submission mechanism');
                            e.preventDefault();
                            
                            const query = document.getElementById('sql-query').value;
                            const formData = new FormData();
                            formData.append('query', query);
                            
                            fetch('/execute-query', {
                                method: 'POST',
                                body: formData
                            })
                            .then(response => response.text())
                            .then(html => {
                                const resultDiv = document.getElementById('query-results');
                                if (resultDiv) {
                                    resultDiv.innerHTML = html;
                                    console.log('Results updated via fallback handler');
                                }
                            })
                            .catch(error => {
                                console.error('Error in fallback submission:', error);
                                alert('Error executing query. Check console for details.');
                            });
                        } else {
                            console.log('HTMX appears to be working, using normal submission');
                        }
                    });
                }
            }
            
            // Call this function after any DOM updates that might affect the form
            function reinitializePage() {
                console.log('Reinitializing page...');
                setupFallbackFormHandler();
                updateLineNumbers();
                
                // Make sure the mode toggle is correctly set
                toggleQueryMode();
                
                // Make sure HTMX is processing the page correctly
                if (typeof htmx !== 'undefined') {
                    htmx.process(document.body);
                }
            }
            
            // Mode toggle function
            function toggleQueryMode() {
                const form = document.getElementById('sql-query-form');
                const sqlLabel = document.getElementById('sql-mode-label');
                const nlLabel = document.getElementById('nl-mode-label');
                const isNLMode = document.getElementById('nl-toggle').checked;
                
                if (isNLMode) {
                    form.classList.add('nl-mode');
                    nlLabel.classList.add('active');
                    sqlLabel.classList.remove('active');
                    document.getElementById('sql-query').placeholder = "Ask a question about your data in plain English...";
                } else {
                    form.classList.remove('nl-mode');
                    sqlLabel.classList.add('active');
                    nlLabel.classList.remove('active');
                    document.getElementById('sql-query').placeholder = "SELECT * FROM table_name LIMIT 10;";
                }
            }
            
            // Handle translation form submission
            function handleTranslateSubmit(event) {
                event.preventDefault();
                console.log("Translation button clicked");
                
                const isNLMode = document.getElementById('nl-toggle').checked;
                if (!isNLMode) {
                    console.log("Not in NL mode, ignoring translate click");
                    return;
                }
                
                const query = document.getElementById('sql-query').value;
                if (!query.trim()) {
                    alert("Please enter a question first");
                    return;
                }
                
                const formData = new FormData();
                formData.append('query', query);
                
                // Show loading state in the main query results area
                const resultsPanel = document.getElementById('query-results');
                resultsPanel.innerHTML = '<div class="p-4 text-center"><div class="animate-pulse">Translating your query...</div></div>';
                
                console.log("Sending translation request");
                
                // Use either htmx or fetch API
                if (typeof htmx !== 'undefined') {
                    htmx.ajax('POST', '/translate-query', {
                        target: '#query-results',
                        swap: 'innerHTML',
                        values: formData
                    });
                } else {
                    fetch('/translate-query', {
                        method: 'POST', 
                        body: formData
                    })
                    .then(response => response.text())
                    .then(html => {
                        resultsPanel.innerHTML = html;
                    })
                    .catch(error => {
                        resultsPanel.innerHTML = `<div class="p-4 bg-red-50 text-red-700 rounded-lg">Error: ${error.message}</div>`;
                    });
                }
            }
        """),
        
        Container(
            # Header with improved styling
            Div(
                Div(
                    H1("DuckDB SQL Editor", cls="text-2xl font-bold"),
                    
                    cls="flex-grow"
                ),
                Div(
                    P(f"Connected to: {DB_PATH}", cls="text-sm text-gray-500"),
                    P(f"Available Tables: {len(tables)}", cls="text-sm text-gray-500"),
                    Button(
                        "Change Database", 
                        cls=ButtonT.secondary + " text-xs px-2 py-1 mt-1",
                        onclick="console.log('Database button clicked'); openModal();"
                    ),
                    cls="text-right header-actions"
                ),
                cls="flex justify-between items-center py-4 border-b border-gray-200 mb-6"
            ),
            
            # Main content area wrapped in a main tag
            Main(
                # Reorganized main layout
                Div(
                    # First row with editor and database tables
                    Div(
                        # Left sidebar with database tables (moved to first position)
                        Div(
                            # Left panels container
                            Div(
                                # Database Tables section
                                Div(
                                    # Header
                                    Div(
                                        H3("Database Tables", cls="text-lg font-semibold"),
                                        P(f"{len(tables)} tables available", cls="text-xs text-gray-500"),
                                        cls="sidebar-section-heading"
                                    ),
                                    # Table list with inline schemas
                                    Div(
                                        *[Div(
                                            # Table header - clickable with toggle indicator
                                            Div(
                                                Div(
                                                    Strong(table, cls="block text-gray-800"),
                                                    Span(f"{len(get_table_schema(table))} columns", cls="column-count")
                                                ),
                                                Span("›", cls="toggle-indicator", id=f"toggle-{table}"),
                                                cls="table-header",
                                                id=f"table-header-{table}",
                                                onclick=f"toggleSchema('{table}')"
                                            ),
                                            # Schema container - hidden by default
                                            Div(
                                                get_table_schema_component(table),
                                                cls="schema-container",
                                                id=f"schema-{table}"
                                            ),
                                            cls="table-item"
                                        ) for table in tables],
                                        cls="schema-section"
                                    ),
                                    cls="border rounded-lg overflow-hidden bg-white shadow-sm h-full"
                                ),
                                cls="left-panels"
                            ),
                            cls="sidebar"
                        ),
                        
                        # SQL editor
                        Card(
                            Div(
                                H3("SQL Query", cls="text-lg font-semibold"),
                                P("Write your SQL query below", cls="text-sm text-gray-500"),
                                cls="flex justify-between items-center mb-3"
                            ),
                            
                            # Add mode toggle container
                            Div(
                                Span("SQL Mode", id="sql-mode-label", cls="mode-label active"),
                                Label(
                                    Input(type="checkbox", id="nl-toggle", onchange="toggleQueryMode()"),
                                    Span(cls="slider"),
                                    cls="switch mx-2"
                                ),
                                Span("Natural Language", id="nl-mode-label", cls="mode-label"),
                                Span("AI Powered", cls="nl-badge"),
                                cls="mode-toggle-container"
                            ),
                            
                            # SQL Query Form
                            Form(
                                Div(
                                    # Query container
                                    Div(
                                        # Editor wrapper to contain line numbers and editor
                                        Div(
                                            # Line numbers container
                                            Pre(id="line-numbers", cls="line-numbers"),
                                            
                                            # Improved SQL editor
                                            Textarea(
                                                id="sql-query",
                                                name="query",
                                                placeholder="SELECT * FROM table_name LIMIT 10;",
                                                cls="sql-editor with-line-numbers w-full h-80 p-3 resize-y"
                                            ),
                                            cls="editor-wrapper"
                                        ),
                                        cls="query-container relative mb-3"
                                    )
                                ),
                                Div(
                                    # SQL execution button
                                    Button("Execute Query", type="submit", 
                                          cls=ButtonT.primary + " px-6 py-2 execute-btn"),
                                    
                                    # Natural language translation button
                                    Button("Translate and run SQL", type="button", 
                                          cls="translate-btn",
                                          onclick="handleTranslateSubmit(event)"),
                                    cls="flex justify-end"
                                ),
                                hx_post="/execute-query",
                                hx_target="#query-results",
                                hx_swap="innerHTML",
                                hx_trigger="submit",
                                id="sql-query-form",
                                cls="mt-2"
                            ),
                            
                            # Remove the separate translation results container since we're using the main query results container
                            
                            cls="shadow-sm flex-1"
                        ),
                        cls="editor-row mb-2" # Reduced margin bottom here
                    ),
                    
                    # Second row with query results (full width)
                    Div(
                        # Query results with tabs
                        Card(
                            Div(
                                H3("Query Results", cls="text-lg font-semibold"),
                                cls="flex justify-between items-center mb-3"
                            ),
                            # Tabs for query history
                            Div(
                                id="query-tabs",
                                cls="query-tabs"
                            ),
                            # Hidden message for when no queries exist
                            P("No queries yet. Execute a query to start building history.", 
                              cls="text-sm text-gray-500 p-2 mx-2",
                              id="no-queries-message"),
                            # Query results container
                            Div(
                                id="query-results", 
                                cls="bg-white result-container query-result-panel p-4"
                            ),
                            cls="shadow-sm"
                        ),
                        cls="results-row flex-grow" # Added flex-grow to take up remaining space
                    ),
                    cls="main-layout"
                ),
                cls="flex-1"
            ),
            
            # Footer with improved styling - modified class
            Div(
                Div(
                    P("Built with FastHTML, MonsterUI and DuckDB", cls="text-sm text-gray-500"),
                    cls="flex-grow"
                ),
                Div(
                    UkIconLink("github", href="https://github.com/AnswerDotAI/MonsterUI", cls="mr-2"),
                    UkIconLink("database", href="https://duckdb.org/docs/"),
                    cls="flex items-center"
                ),
                cls="flex justify-between items-center p-4 footer"
            ),
            
            # Modal backdrop (separate element)
            Div(
                id="modalBackdrop",
                cls="modal-backdrop",
                onclick="closeModal()"
            ),
            
            # Database selection modal container - simplified
            Div(
                id="modalContainer",
                cls="modal-container",
                style="background-color: white; border: 2px solid black;"
            ),
            
            # Add Modal CSS
            Style("""
                .modal-container {
                    display: none;
                    padding: 20px;
                    box-sizing: border-box;
                    min-height: 300px;
                }
                
                .modal-header {
                    display: flex;
                    justify-content: space-between;
                    align-items: center;
                    padding-bottom: 10px;
                    border-bottom: 1px solid #eee;
                    margin-bottom: 15px;
                }
                
                .modal-body {
                    padding: 10px 0;
                    margin-bottom: 15px;
                    flex: 1;
                }
                
                .modal-footer {
                    display: flex;
                    justify-content: flex-end;
                    padding-top: 10px;
                    border-top: 1px solid #eee;
                }
                
                .separator {
                    display: flex;
                    align-items: center;
                    text-align: center;
                    margin: 15px 0;
                }
                
                .separator::before,
                .separator::after {
                    content: '';
                    flex: 1;
                    border-bottom: 1px solid #eee;
                }
                
                .separator-text {
                    padding: 0 10px;
                    color: #888;
                }
                
                .form-group {
                    margin-bottom: 15px;
                }
                
                /* Fix for upload file section */
                #upload-form {
                    display: block;
                    width: 100%;
                }
                
                /* Make sure all form controls are visible */
                input, button, label, p, h3 {
                    display: block;
                    visibility: visible !important;
                    opacity: 1 !important;
                }
            """),
            
            # Modal script
            Script("""
                // Open the modal
                function openModal() {
                    console.log('Opening modal');
                    const backdrop = document.getElementById('modalBackdrop');
                    const container = document.getElementById('modalContainer');
                    
                    if (backdrop && container) {
                        console.log('Modal elements found, showing modal');
                        
                        // Force styles directly
                        backdrop.style.position = 'fixed';
                        backdrop.style.top = '0';
                        backdrop.style.left = '0';
                        backdrop.style.width = '100%';
                        backdrop.style.height = '100%';
                        backdrop.style.backgroundColor = 'rgba(0, 0, 0, 0.5)';
                        backdrop.style.zIndex = '9998';
                        backdrop.style.display = 'block';
                        
                        container.style.position = 'fixed';
                        container.style.top = '50%';
                        container.style.left = '50%';
                        container.style.transform = 'translate(-50%, -50%)';
                        container.style.backgroundColor = 'white';
                        container.style.border = '1px solid #ccc';
                        container.style.borderRadius = '8px';
                        container.style.boxShadow = '0 4px 8px rgba(0, 0, 0, 0.1)';
                        container.style.zIndex = '9999';
                        container.style.width = '90%';
                        container.style.maxWidth = '500px';
                        container.style.minHeight = '300px'; 
                        container.style.maxHeight = '90vh';
                        container.style.overflowY = 'auto';
                        container.style.display = 'block';
                        container.style.padding = '20px';
                        
                        // Create modal content using innerHTML to ensure it's rendered
                        container.innerHTML = `
                            <div class="modal-header">
                                <h3 class="text-lg font-semibold">Connect to a DuckDB Database</h3>
                                <button class="text-gray-400 hover:text-gray-500 text-xl font-bold" onclick="closeModal()">×</button>
                            </div>
                            
                            <div class="modal-body">                                
                                <form id="upload-form" class="mb-4">
                                    <div class="form-group mb-3">
                                        <label for="db_file" class="block mb-1 font-medium">Choose File:</label>
                                        <input type="file" id="db_file" name="db_file" accept=".duckdb,.db" class="w-full px-3 py-2 border rounded">
                                    </div>
                                    
                                    <div class="flex justify-end mt-4">
                                        <button type="submit" id="upload-btn" class="bg-blue-500 hover:bg-blue-600 text-white px-4 py-2 rounded"
                                            hx-post="/change-database" hx-target="#result-area" hx-swap="innerHTML" hx-encoding="multipart/form-data">Connect</button>
                                    </div>
                                </form>
                                <div id="result-area" class="mt-2"></div>
                            </div>
                        `;
                        
                        // Add htmx event handlers after content is injected
                        setupFormHandlers();
                        
                        document.body.style.overflow = 'hidden'; // Prevent scrolling
                        
                        // Debug info
                        console.log('Backdrop z-index:', getComputedStyle(backdrop).zIndex);
                        console.log('Modal z-index:', getComputedStyle(container).zIndex);
                        console.log('Backdrop display:', getComputedStyle(backdrop).display);
                        console.log('Modal display:', getComputedStyle(container).display);
                        console.log('Modal background-color:', getComputedStyle(container).backgroundColor);
                        console.log('Modal dimensions:', container.offsetWidth, 'x', container.offsetHeight);
                        console.log('Modal position:', container.offsetLeft, ',', container.offsetTop);
                        console.log('Modal has children:', container.children.length);
                    } else {
                        console.error('Modal elements not found!', {
                            backdrop: backdrop,
                            container: container
                        });
                    }
                }
                
                // Close the modal
                function closeModal() {
                    console.log('Closing modal');
                    const backdrop = document.getElementById('modalBackdrop');
                    const container = document.getElementById('modalContainer');
                    
                    // Check if we should reload the page due to database change
                    const resultArea = document.getElementById('result-area');
                    const shouldReload = resultArea && 
                        resultArea.textContent && 
                        resultArea.textContent.includes('Successfully connected to');
                    
                    if (backdrop && container) {
                        backdrop.style.display = 'none';
                        container.style.display = 'none';
                        document.body.style.overflow = ''; // Allow scrolling
                    }
                    
                    // Clear any previous messages
                    if (resultArea) {
                        resultArea.innerHTML = '';
                    }
                    
                    // If database was changed successfully, reload the page
                    if (shouldReload) {
                        console.log('Database changed successfully. Reloading page...');
                        window.location.reload();
                    }
                }
                
                // Initialize modal when the document is loaded
                document.addEventListener('DOMContentLoaded', function() {
                    console.log('Initializing modal');
                    const backdrop = document.getElementById('modalBackdrop');
                    const container = document.getElementById('modalContainer');
                    
                    if (backdrop && container) {
                        console.log('Modal elements found during initialization');
                        // Ensure z-index is set correctly
                        backdrop.style.zIndex = '9998';
                        container.style.zIndex = '9999';
                    } else {
                        console.error('Modal elements not found during initialization!');
                    }
                });
                
                // Setup htmx form handlers
                function setupFormHandlers() {
                    const uploadForm = document.getElementById('upload-form');
                    if (uploadForm) {
                        console.log('Found upload form, adding event listener');
                        uploadForm.addEventListener('submit', function(e) {
                            e.preventDefault();
                            
                            // Show loading state
                            const uploadBtn = document.getElementById('upload-btn');
                            if (uploadBtn) {
                                uploadBtn.disabled = true;
                                uploadBtn.innerHTML = 'Connecting...';
                            }
                            
                            const formData = new FormData(uploadForm);
                            const fileInput = document.getElementById('db_file');
                            
                            // Validate file extension
                            if (fileInput && fileInput.files.length > 0) {
                                const filename = fileInput.files[0].name;
                                if (!filename.endsWith('.duckdb') && !filename.endsWith('.db')) {
                                    document.getElementById('result-area').innerHTML = `
                                        <div class="bg-red-50 border border-red-400 text-red-700 px-4 py-3 rounded relative">
                                            <strong>Error!</strong>
                                            <p>Please select a valid .duckdb or .db file</p>
                                        </div>
                                    `;
                                    if (uploadBtn) {
                                        uploadBtn.disabled = false;                                    }
                                    return;
                                }
                            }
                            
                            fetch('/change-database', {
                                method: 'POST',
                                body: formData
                            })
                            .then(response => response.json())
                            .then(data => {
                                const resultArea = document.getElementById('result-area');
                                if (data.success) {
                                    resultArea.innerHTML = `
                                        <div class="bg-green-50 border border-green-400 text-green-700 px-4 py-3 rounded relative">
                                            <strong>Success!</strong>
                                            <p>${data.message}</p>
                                            <p class="mt-2">Reloading page in 2 seconds...</p>
                                        </div>
                                    `;
                                    // Automatically reload after successful connection
                                    setTimeout(() => window.location.reload(), 2000);
                                } else {
                                    resultArea.innerHTML = `
                                        <div class="bg-red-50 border border-red-400 text-red-700 px-4 py-3 rounded relative">
                                            <strong>Error!</strong>
                                            <p>${data.message}</p>
                                        </div>
                                    `;
                                    if (uploadBtn) {
                                        uploadBtn.disabled = false;
                                    }
                                }
                            })
                            .catch(error => {
                                document.getElementById('result-area').innerHTML = `
                                    <div class="bg-red-50 border border-red-400 text-red-700 px-4 py-3 rounded relative">
                                        <strong>Error!</strong>
                                        <p>An unexpected error occurred</p>
                                    </div>
                                `;
                                if (uploadBtn) {
                                    uploadBtn.disabled = false;
                                    uploadBtn.innerHTML = 'Upload and Connect';
                                }
                            });
                        });
                    }
                }
                
                // Handle response from database change
                document.body.addEventListener('htmx:afterRequest', function(evt) {
                    if (evt.detail.target && evt.detail.target.id === 'result-area') {
                        if (evt.detail.successful) {
                            try {
                                const response = JSON.parse(evt.detail.xhr.response);
                                const resultArea = document.getElementById('result-area');
                                
                                if (response.success) {
                                    resultArea.innerHTML = `
                                        <div class="bg-green-50 border border-green-400 text-green-700 px-4 py-3 rounded relative">
                                            <strong>Success!</strong>
                                            <p>${response.message}</p>
                                            <p class="mt-2">
                                                <button onclick="reloadPage()" class="text-green-700 underline">
                                                    Reload the page to use the new database
                                                </button>
                                            </p>
                                        </div>
                                    `;
                                } else {
                                    resultArea.innerHTML = `
                                        <div class="bg-red-50 border border-red-400 text-red-700 px-4 py-3 rounded relative">
                                            <strong>Error!</strong>
                                            <p>${response.message}</p>
                                        </div>
                                    `;
                                }
                            } catch (e) {
                                // If not JSON, display the raw response
                                document.getElementById('result-area').innerHTML = evt.detail.xhr.response;
                            }
                        }
                    }
                });
                
                function reloadPage() {
                    window.location.reload();
                }
            """),
            
            cls="mx-auto px-4 sm:px-6 lg:px-8 max-w-full w-[98%] container"
        )
    )
    
    return result

def get_table_schema_component(table_name):
    """Generate a component showing the schema for a table"""
    if not table_name:
        return P("Invalid table name", cls="text-red-500 text-sm")
    
    try:
        schema = get_table_schema(table_name)
        if not schema:
            return P(f"No schema found for table: {table_name}", cls="text-red-500 text-sm")
        
        return Div(
            # Schema header with action button
            Div(
                P(f"Schema", cls="schema-header"),
               
                # Column list using a more compact design
                Ul(
                    *[Li(
                        Span(col[0], cls="column-name"),
                        Span(col[1], cls="column-type"),
                        Span("✓" if col[3] else "✗", 
                             cls=f"column-nullable {'text-green-600' if col[3] else 'text-red-500'}")
                    , cls="schema-column-item") for col in schema],
                    cls="schema-column-list"
                ),
                cls="p-2"
            )
        )
    except Exception as e:
        print(f"Error generating schema component for table {table_name}: {e}")
        return P(f"Error loading schema: {str(e)}", cls="text-red-500 text-sm")

@rt('/table/{table_name}')
def table_info(table_name):
    """Get schema information for a specific table"""
    if not table_name:
        return Div(P("Invalid table name", cls="text-red-500"))
    
    schema = get_table_schema(table_name)
    
    return Div(
        Div(
            H4(f"Schema for: {table_name}", cls="text-lg font-semibold"),
            Button("Query Table", 
                   cls=ButtonT.secondary + " text-sm px-3 py-1", 
                   hx_on=f"click: document.getElementById('sql-query').value = `SELECT * FROM {table_name} LIMIT 10;`; updateLineNumbers()"),
            cls="flex justify-between items-center mb-3"
        ),
        Div(
            Table(
                Thead(Tr(*[Th(col, cls="px-4 py-2 text-left text-xs font-medium text-gray-500 uppercase tracking-wider") 
                            for col in ["Column Name", "Type", "Nullable"]])),
                Tbody(*[Tr(
                        Td(col[0], cls="px-4 py-2 whitespace-nowrap font-medium text-gray-900"),
                        Td(col[1], cls="px-4 py-2 whitespace-nowrap font-mono text-xs text-gray-600 bg-gray-50"),
                        Td("Yes" if col[3] else "No", 
                           cls=f"px-4 py-2 whitespace-nowrap text-sm {'text-green-600' if col[3] else 'text-red-600'}")
                       ) for col in schema],
                      cls="divide-y divide-gray-200"
                ),
                cls="min-w-full divide-y divide-gray-200 table-fixed"
            ),
            cls="shadow overflow-hidden border-b border-gray-200 sm:rounded-lg bg-white"
        ),
        P("Click a column name to copy it to the query editor", cls="text-xs text-gray-500 mt-2"),
        cls="p-1"
    )

# Helper to check if a value might be JSON
def is_json(value):
    """Check if a value looks like it might be JSON"""
    if not isinstance(value, str):
        return False
    
    # Quick check for JSON-like structure
    value = value.strip()
    if not ((value.startswith('{') and value.endswith('}')) or 
            (value.startswith('[') and value.endswith(']'))):
        return False
    
    # Try to parse as JSON
    try:
        json.loads(value)
        return True
    except:
        return False

# Helper to truncate text for display
def truncate_text(text, max_length=100):
    """Truncate text to max_length and add ellipsis if needed"""
    if len(text) <= max_length:
        return text
    return text[:max_length] + '...'

# Update the run_query function to handle JSON data
@rt('/execute-query', methods=['POST'])
async def run_query(request):
    """Execute a SQL query and return the results"""
    print("==== Starting run_query function ====")
    
    try:
        # Get form data correctly from the request
        print("Getting form data from request...")
        form_data = await request.form()
        query = form_data.get('query', '')
        print(f"Received query: {query[:50]}...")
        
        if not query.strip():
            print("Empty query received, returning error")
            return Div(
                Div(
                    Strong("Error: ", cls="font-bold"),
                    Span("Please enter a query"),
                    cls="p-4 bg-red-50 text-red-700 rounded-lg flex items-center"
                ),
                cls="my-4 single-query-result"
            )
        
        # Start timer for query execution
        import time
        import datetime
        import json
        start_time = time.time()
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        
        print("About to execute query...")
        results = execute_query(query)
        print("Query executed, processing results...")
        
        # Calculate execution time
        execution_time = time.time() - start_time
        
        # Properly escape the query for JavaScript
        # Use JSON encoding which handles all the escaping for us
        escaped_query = json.dumps(query)
        
        # JavaScript to add query to history and ensure form functionality persists
        history_script = Script(f"""
            // Add this query to history
            console.log("Adding query to history: {timestamp}");
            addQueryToHistory({escaped_query}, "{timestamp}");
            
            // CRITICAL: Re-initialize the form binding
            (function() {{
                console.log("Reinitializing form handlers");
                
                // Wait a moment for HTMX to complete its work
                setTimeout(function() {{
                    const form = document.querySelector('form[hx-post="/execute-query"]');
                    if (form) {{
                        console.log("Form found, ensuring htmx binding");
                        
                        // First, remove any existing event listeners by cloning the form
                        const parent = form.parentNode;
                        const clone = form.cloneNode(true);
                        parent.replaceChild(clone, form);
                        
                        // Re-process with HTMX
                        if (typeof htmx !== 'undefined') {{
                            console.log("Processing form with HTMX");
                            htmx.process(clone);
                        }}
                    }} else {{
                        console.error("Form not found!");
                    }}
                    
                    // Extra debug info
                    console.log("Form state:", {{
                        "formExists": !!document.querySelector('form[hx-post="/execute-query"]'),
                        "htmxLoaded": typeof htmx !== 'undefined'
                    }});
                    
                    // Use our more comprehensive page reinitialization
                    if (typeof reinitializePage === 'function') {{
                        reinitializePage();
                    }}
                }}, 10);
            }})();
        """)
        
        if "error" in results:
            print(f"Query error: {results['error']}")
            return Div(
                history_script,
                Div(
                    Strong("SQL Error: ", cls="font-bold"),
                    P(results["error"], cls="mt-2 font-mono text-sm p-3 bg-red-100 rounded overflow-x-auto"),
                    cls="p-4 bg-red-50 text-red-700 rounded-lg"
                ),
                cls="single-query-result"
            )
        
        # Limit display to 100 rows for performance
        display_data = results["data"][:100]
        total_rows = len(results["data"])
        
        if not display_data:
            print("Query returned no results")
            return Div(
                history_script,
                Div(
                    Strong("Query completed ", cls="font-bold"),
                    Span(f"in {execution_time:.2f}s"),
                    P("No results returned", cls="text-sm"),
                    cls="p-4 bg-green-50 text-green-700 rounded-lg"
                ),
                cls="single-query-result"
            )
            
        print(f"Processing {len(display_data)} rows for display")
        
        # Create table rows with special handling for JSON data
        rows = []
        for row_data in display_data:
            cells = []
            for i, cell in enumerate(row_data):
                cell_str = str(cell)
                column_name = results["columns"][i]
                
                # Check if cell could be JSON
                if is_json(cell_str):
                    # Create a JSON cell with prettifier and explorer
                    cells.append(
                        Td(
                            Div(
                                Div(
                                    Span(truncate_text(cell_str, 50), cls="json-text"),
                                    Span("JSON", cls="json-badge"),
                                    cls="cursor-pointer",
                                    onclick=f"toggleJsonPrettify(this)"
                                ),
                                Div(
                                    # This div will be filled with prettified JSON via JavaScript
                                    cls="json-prettified",
                                    style="display: none;"
                                ),
                                Button(
                                    "Explore JSON", 
                                    cls="mt-2 text-xs bg-blue-50 text-blue-600 px-2 py-1 rounded border border-blue-200 hover:bg-blue-100",
                                    onclick=f"openJsonExplorer({json.dumps(cell_str)}, '{column_name}')"
                                ),
                                data_json=cell_str,
                                cls="json-cell p-2"
                            ),
                            cls="whitespace-nowrap text-sm text-gray-900"
                        )
                    )
                else:
                    # Regular cell
                    cells.append(
                        Td(
                            cell_str, 
                            cls="px-4 py-2 whitespace-nowrap text-sm text-gray-900 truncate max-w-[300px]"
                        )
                    )
            
            rows.append(Tr(*cells, cls="hover:bg-gray-50"))
        
        print("Building final response...")
        
        # Build response
        response = Div(
            history_script,
            Div(
                Div(
                    Strong("Query successful ", cls="font-bold"),
                    Span(f"({execution_time:.2f}s)"),
                    cls="text-green-700"
                ),
                Div(
                    Span(f"Showing {len(display_data)} of {total_rows} rows", 
                       cls="text-sm text-gray-500"),
                    cls="mt-1"
                ),
                cls="mb-4 p-3 bg-green-50 rounded-lg"
            ),
            Div(
                Div(
                    Table(
                        Thead(
                            Tr(*[Th(col, cls="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider") 
                                for col in results["columns"]])
                        ),
                        Tbody(*rows, cls="bg-white divide-y divide-gray-200"),
                        cls="min-w-full divide-y divide-gray-200 result-table"
                    ),
                    cls="table-wrapper"
                ),
                cls="shadow border-b border-gray-200 rounded-lg"
            ),
            cls="py-2 single-query-result"
        )
        
        print("==== run_query function completed successfully ====")
        return response
        
    except Exception as e:
        import traceback
        print(f"=== CRITICAL ERROR IN run_query: {str(e)} ===")
        print(traceback.format_exc())
        
        # Return a user-friendly error message
        return Div(
            Div(
                Strong("Application Error: ", cls="font-bold"),
                P(f"An unexpected error occurred: {str(e)}", 
                  cls="mt-2 font-mono text-sm p-3 bg-red-100 rounded overflow-x-auto"),
                cls="p-4 bg-red-50 text-red-700 rounded-lg"
            ),
            cls="my-4 single-query-result"
        )

@rt('/debug', methods=['GET', 'POST'])
async def debug(request):
    """Debug endpoint to verify the app is still accepting requests"""
    import datetime
    timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    
    request_info = {
        "timestamp": timestamp,
        "method": "GET" if request.method == "GET" else "POST",
        "headers": dict(request.headers),
    }
    
    print(f"Debug endpoint accessed: {timestamp}")
    
    return Div(
        H3("App is Running", cls="text-lg font-semibold text-green-600"),
        P(f"Current time: {timestamp}", cls="text-sm"),
        P(f"Request method: {request_info['method']}", cls="text-sm"),
        P("This endpoint confirms the application is still accepting requests.", cls="mt-2 text-sm"),
        Button("Return to Editor", cls=ButtonT.secondary, 
               onclick="window.location.href='/'"),
        cls="p-4 bg-white shadow rounded-lg"
    )

@rt('/reset-connection', methods=['GET'])
async def reset_connection_endpoint(request):
    """Endpoint to reset the database connection"""
    success = reset_connection()
    
    if success:
        return Div(
            H3("Connection Reset Successful", cls="text-lg font-semibold text-green-600"),
            P("The database connection has been successfully reset.", cls="text-sm"),
            Button("Return to Editor", cls=ButtonT.secondary, 
                   onclick="window.location.href='/'"),
            cls="p-4 bg-white shadow rounded-lg"
        )
    else:
        return Div(
            H3("Connection Reset Failed", cls="text-lg font-semibold text-red-600"),
            P("Failed to reset the database connection. Check server logs for details.", 
              cls="text-sm"),
            Button("Try Again", cls=ButtonT.destructive, 
                   onclick="window.location.reload()"),
            Button("Return to Editor", cls=ButtonT.secondary, 
                   onclick="window.location.href='/'"),
            cls="p-4 bg-white shadow rounded-lg"
        )

@rt('/change-database', methods=['POST'])
async def change_database_endpoint(request):
    """Endpoint to change the database file by uploading a new one"""
    try:
        # Get the form data
        form_data = await request.form()
        
        # Handle file upload
        if 'db_file' in form_data:
            file = form_data['db_file']
            if not file.filename:
                return {"success": False, "message": "No file selected"}
            
            # Validate file extension
            if not (file.filename.endswith('.duckdb') or file.filename.endswith('.db')):
                return {"success": False, "message": "Invalid file type. Please upload a .duckdb or .db file"}
            
            # Create a temp directory if it doesn't exist
            temp_dir = Path("./temp_db")
            temp_dir.mkdir(exist_ok=True)
            
            # Save the file
            file_path = temp_dir / file.filename
            with open(file_path, 'wb') as f:
                f.write(await file.read())
            
            # Try to connect to the new database
            success, error = reset_with_new_db(str(file_path))
            if success:
                return {"success": True, "message": f"Successfully connected to {file.filename}"}
            else:
                # Clean up the file if connection failed
                if file_path.exists():
                    file_path.unlink()
                return {"success": False, "message": f"Failed to connect: {error}"}
        else:
            return {"success": False, "message": "No file uploaded"}
    except Exception as e:
        print(f"Error in change-database: {e}")
        return {"success": False, "message": f"An error occurred: {str(e)}"}

# Function to clean up resources
def cleanup_resources():
    """Close database connection and clean up resources"""
    global _db_connection
    if _db_connection is not None:
        print("Closing database connection on shutdown")
        try:
            _db_connection.close()
            _db_connection = None
        except Exception as e:
            print(f"Error closing database connection: {e}")
    
    # Clean up temporary database directory
    try:
        temp_dir = Path("./temp_db")
        if temp_dir.exists():
            import shutil
            print("Cleaning up temporary database directory")
            shutil.rmtree(temp_dir)
    except Exception as e:
        print(f"Error cleaning up temporary files: {e}")

def get_database_schema_info():
    """Get comprehensive schema information for all tables to inform AI translation"""
    tables = get_table_names()
    schema_info = {}
    
    # Process all tables
    for table in tables:
        try:
            # Get schema
            schema = get_table_schema(table)
            
            # Extract column names
            column_names = [col[0] for col in schema]
            
            # Initialize table info with columns
            schema_info[table] = {
                "columns": [{"name": col[0], "type": col[1], "nullable": col[3]} for col in schema],
            }
            
        except Exception as e:
            print(f"Error getting schema info for table {table}: {e}")
            schema_info[table] = {"error": str(e)}
    
    return schema_info

def format_for_openai(schema_info):
    """Format schema info into a more compact, readable text format for OpenAI"""
    formatted_text = []
    
    for table_name, table_info in schema_info.items():
        formatted_text.append(f"TABLE: {table_name}")
        
        # Format columns
        formatted_text.append("COLUMNS:")
        for col in table_info.get('columns', []):
            nullable = "NULL" if col.get('nullable', False) else "NOT NULL"
            formatted_text.append(f"  - {col['name']} ({col['type']}, {nullable})")
        
        # Format sample data if available
        sample_data = table_info.get('sample_data', [])
        if sample_data:
            formatted_text.append(f"\nSAMPLE DATA ({len(sample_data)} rows):")
            
            # Create a compact representation of each row
            for i, row in enumerate(sample_data):
                row_str = []
                for col, val in row.items():
                    # Truncate long values
                    if len(val) > 50:
                        val = val[:47] + "..."
                    row_str.append(f"{col}={val}")
                
                formatted_text.append(f"  ROW {i+1}: {', '.join(row_str)}")
    
    return "\n".join(formatted_text)

def translate_natural_language_to_sql(natural_language_query):
    """Translate a natural language query to DuckDB SQL using OpenAI"""
    api_key = os.getenv("OPENAI_API_KEY")
    if not api_key:
        return {"error": "OpenAI API key not configured. Please add OPENAI_API_KEY to your .env file."}
    
    try:
        # Get database schema info
        schema_info = get_database_schema_info()
        
        # Format the schema info for OpenAI in a more compact way
        formatted_schema = format_for_openai(schema_info)
        
        # Log the size of different components
        schema_json_size = len(json.dumps(schema_info, indent=2))
        formatted_schema_size = len(formatted_schema)
        query_size = len(natural_language_query)
        
        print("\n=== DATA SIZE ANALYSIS ===")
        print(f"Original JSON schema size: {schema_json_size} characters")
        print(f"Formatted schema size: {formatted_schema_size} characters")
        print(f"Size reduction: {schema_json_size - formatted_schema_size} characters ({(schema_json_size - formatted_schema_size) / schema_json_size * 100:.1f}%)")
        print(f"Query size: {query_size} characters")
        print(f"Total content size: {formatted_schema_size + query_size + 100} characters (approx)")  # 100 for the template text
        
        # Log schema details
        if 'requests' in schema_info:
            columns_count = len(schema_info['requests'].get('columns', []))
            sample_rows = len(schema_info['requests'].get('sample_data', []))
            print(f"Requests table: {columns_count} columns in schema, {sample_rows} sample rows")
        
        # Create the content for sending to OpenAI
        prompt_content = f"""Database Schema:
{formatted_schema}

Natural Language Query:
{natural_language_query}

Translate this into a valid DuckDB SQL query:"""
        
        # Log the data being sent to OpenAI
        print("\n=== DATA SENT TO OPENAI ===")
        print(prompt_content[:500] + "..." if len(prompt_content) > 500 else prompt_content)
        print(f"\n=== TOTAL LENGTH: {len(prompt_content)} characters ===")
        
        # Construct the prompt for OpenAI
        prompt = {
            "model": "gpt-4o",
            "messages": [
                {"role": "system", "content": """You are a DuckDB SQL expert. Translate natural language queries into valid DuckDB SQL queries.
Use the database schema and sample data provided to inform your translations.
If you need information about DuckDB SQL syntax or specific functions, consult https://duckdb.org/llms.txt
Always use date formatting functions from https://duckdb.org/docs/stable/sql/functions/date.html when dealing with dates or timestamps.
Return ONLY the SQL query NEVER ANYTHING ELSE like explanations or markdown formatting or ticks"""},
                {"role": "user", "content": prompt_content}
            ]
        }
        
        # Estimate token count (very rough approximation)
        estimated_tokens = len(prompt_content) / 4 + 100  # 4 chars per token + 100 for system message
        print(f"Estimated tokens: ~{int(estimated_tokens)}")
        
        # Call OpenAI API
        response = requests.post(
            "https://api.openai.com/v1/chat/completions",
            headers={
                "Authorization": f"Bearer {api_key}",
                "Content-Type": "application/json"
            },
            json=prompt
        )
        
        if response.status_code != 200:
            return {"error": f"OpenAI API error: {response.text}"}
        
        # Extract the SQL query from the response
        result = response.json()
        sql_query = result["choices"][0]["message"]["content"].strip()
        
        # Strip any markdown code formatting (```SQL, ```, etc.)
        # Remove opening code block markers like ```sql, ```SQL, or just ```
        if sql_query.startswith("```"):
            # Find the first line break which would be after the ```sql or similar
            first_line_break = sql_query.find('\n')
            if first_line_break != -1:
                sql_query = sql_query[first_line_break+1:]
            else:
                # If no line break, just remove the first three backticks
                sql_query = sql_query[3:]
        
        # Remove closing code block markers
        if sql_query.endswith("```"):
            sql_query = sql_query[:-3]
        
        # Final trimming to remove any extra whitespace
        sql_query = sql_query.strip()
        
        # Log the generated SQL query
        print("\n=== GENERATED SQL QUERY ===")
        print(sql_query)
        print("===========================\n")
        
        return {"sql": sql_query}
    
    except Exception as e:
        import traceback
        print(f"Error translating query: {e}")
        print(traceback.format_exc())
        return {"error": f"Translation error: {str(e)}"}

@rt('/translate-query', methods=['POST'])
async def translate_query_endpoint(request):
    """Endpoint to translate natural language to SQL and automatically execute it"""
    print("==== Starting translate_query endpoint ====")
    
    try:
        # Get form data
        form_data = await request.form()
        natural_language_query = form_data.get('query', '')
        print(f"Received natural language query: {natural_language_query[:100]}...")
        
        if not natural_language_query.strip():
            return Div(
                Strong("Error: ", cls="font-bold"),
                Span("Please enter a query"),
                cls="p-4 bg-red-50 text-red-700 rounded-lg flex items-center"
            )
        
        # Translate the query
        print("Translating query...")
        result = translate_natural_language_to_sql(natural_language_query)
        
        if "error" in result:
            print(f"Translation error: {result['error']}")
            return Div(
                Strong("Translation Error: ", cls="font-bold"),
                P(result["error"], cls="mt-2 font-mono text-sm p-3 bg-red-100 rounded overflow-x-auto"),
                cls="p-4 bg-red-50 text-red-700 rounded-lg"
            )
        
        # Get the SQL query and add the original natural language as a comment
        sql_query = f"-- Natural Language: {natural_language_query}\n\n{result['sql']}"
        print(f"Successfully translated to SQL: {sql_query[:100]}...")
        
        # Update the SQL editor with the translated query
        import json
        sql_query_escaped = json.dumps(sql_query)
        
        # Execute the query (use the actual SQL part, not the comment)
        print("Automatically executing the translated query...")
        execution_results = execute_query(result["sql"])
        
        # Generate timestamp for query history
        import datetime
        import time
        start_time = time.time()
        timestamp = datetime.datetime.now().strftime("%H:%M:%S")
        execution_time = time.time() - start_time
        
        # JavaScript to add query to history
        history_script = Script(f"""
            // Update the SQL editor with the translated query
            document.getElementById('sql-query').value = {sql_query_escaped};
            updateLineNumbers();
            
            // Add this query to history
            console.log("Adding translated query to history: {timestamp}");
            addQueryToHistory({sql_query_escaped}, "{timestamp}");
            
            // CRITICAL: Re-initialize the form binding
            (function() {{
                console.log("Reinitializing form handlers");
                
                // Wait a moment for HTMX to complete its work
                setTimeout(function() {{
                    const form = document.querySelector('form[hx-post="/execute-query"]');
                    if (form) {{
                        console.log("Form found, ensuring htmx binding");
                        
                        // First, remove any existing event listeners by cloning the form
                        const parent = form.parentNode;
                        const clone = form.cloneNode(true);
                        parent.replaceChild(clone, form);
                        
                        // Re-process with HTMX
                        if (typeof htmx !== 'undefined') {{
                            console.log("Processing form with HTMX");
                            htmx.process(clone);
                        }}
                    }} else {{
                        console.error("Form not found!");
                    }}
                    
                    // Extra debug info
                    console.log("Form state:", {{
                        "formExists": !!document.querySelector('form[hx-post="/execute-query"]'),
                        "htmxLoaded": typeof htmx !== 'undefined'
                    }});
                    
                    // Use our more comprehensive page reinitialization
                    if (typeof reinitializePage === 'function') {{
                        reinitializePage();
                    }}
                }}, 10);
            }})();
        """)
        
        # Display error if there was a problem executing the query
        if "error" in execution_results:
            print(f"Query execution error: {execution_results['error']}")
            return Div(
                history_script,
                Div(
                    Strong("SQL Error: ", cls="font-bold"),
                    P(execution_results["error"], cls="mt-2 font-mono text-sm p-3 bg-red-100 rounded overflow-x-auto"),
                    cls="p-4 bg-red-50 text-red-700 rounded-lg"
                ),
                cls="single-query-result"
            )
        
        # Process results similar to run_query function
        # Limit display to 100 rows for performance
        display_data = execution_results["data"][:100]
        total_rows = len(execution_results["data"])
        
        if not display_data:
            print("Query returned no results")
            return Div(
                history_script,
                Div(
                    Strong("Query completed ", cls="font-bold"),
                    Span(f"in {execution_time:.2f}s"),
                    P("No results returned", cls="text-sm"),
                    cls="p-4 bg-green-50 text-green-700 rounded-lg"
                ),
                cls="single-query-result"
            )
        
        print(f"Processing {len(display_data)} rows for display")
        
        # Create table rows with special handling for JSON data
        rows = []
        for row_data in display_data:
            cells = []
            for i, cell in enumerate(row_data):
                cell_str = str(cell)
                column_name = execution_results["columns"][i]
                
                # Check if cell could be JSON
                if is_json(cell_str):
                    # Create a JSON cell with prettifier and explorer
                    cells.append(
                        Td(
                            Div(
                                Div(
                                    Span(truncate_text(cell_str, 50), cls="json-text"),
                                    Span("JSON", cls="json-badge"),
                                    cls="cursor-pointer",
                                    onclick=f"toggleJsonPrettify(this)"
                                ),
                                Div(
                                    # This div will be filled with prettified JSON via JavaScript
                                    cls="json-prettified",
                                    style="display: none;"
                                ),
                                Button(
                                    "Explore JSON", 
                                    cls="mt-2 text-xs bg-blue-50 text-blue-600 px-2 py-1 rounded border border-blue-200 hover:bg-blue-100",
                                    onclick=f"openJsonExplorer({json.dumps(cell_str)}, '{column_name}')"
                                ),
                                data_json=cell_str,
                                cls="json-cell p-2"
                            ),
                            cls="whitespace-nowrap text-sm text-gray-900"
                        )
                    )
                else:
                    # Regular cell
                    cells.append(
                        Td(
                            cell_str, 
                            cls="px-4 py-2 whitespace-nowrap text-sm text-gray-900 truncate max-w-[300px]"
                        )
                    )
            
            rows.append(Tr(*cells, cls="hover:bg-gray-50"))
        
        # Build final response using the same format as regular SQL queries
        return Div(
            history_script,
            Div(
                Div(
                    Strong("Query successful ", cls="font-bold"),
                    Span(f"({execution_time:.2f}s)"),
                    cls="text-green-700"
                ),
                Div(
                    Span(f"Showing {len(display_data)} of {total_rows} rows", 
                       cls="text-sm text-gray-500"),
                    cls="mt-1"
                ),
                cls="mb-4 p-3 bg-green-50 rounded-lg"
            ),
            Div(
                Div(
                    Table(
                        Thead(
                            Tr(*[Th(col, cls="px-4 py-3 text-left text-xs font-medium text-gray-500 uppercase tracking-wider") 
                                for col in execution_results["columns"]])
                        ),
                        Tbody(*rows, cls="bg-white divide-y divide-gray-200"),
                        cls="min-w-full divide-y divide-gray-200 result-table"
                    ),
                    cls="table-wrapper"
                ),
                cls="shadow border-b border-gray-200 rounded-lg"
            ),
            cls="py-2 single-query-result"
        )
        
    except Exception as e:
        import traceback
        print(f"=== CRITICAL ERROR IN translate_query: {str(e)} ===")
        print(traceback.format_exc())
        
        return Div(
            Strong("Application Error: ", cls="font-bold"),
            P(f"An unexpected error occurred: {str(e)}", 
              cls="mt-2 font-mono text-sm p-3 bg-red-100 rounded overflow-x-auto"),
            cls="p-4 bg-red-50 text-red-700 rounded-lg"
        )

if __name__ == "__main__":
    # Register cleanup function to run on exit
    atexit.register(cleanup_resources)
    serve() 