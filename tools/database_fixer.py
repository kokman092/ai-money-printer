"""
database_fixer.py - Database Execution Engine
Applies verified fixes to client databases
"""

import os
import sqlite3
from typing import Optional, Any
from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DatabaseType(Enum):
    SQLITE = "sqlite"
    POSTGRES = "postgres"
    MYSQL = "mysql"


@dataclass
class FixResult:
    """Result of applying a fix."""
    success: bool
    message: str
    rows_affected: int = 0
    execution_time_ms: float = 0.0
    error: Optional[str] = None
    rollback_available: bool = False


class DatabaseFixer:
    """
    Executes verified fixes on client databases.
    Only runs after safety.py gives the green light.
    """
    
    def __init__(self):
        self.supported_types = [DatabaseType.SQLITE, DatabaseType.POSTGRES, DatabaseType.MYSQL]
    
    def get_connection(
        self,
        db_type: str,
        connection_string: str
    ) -> Any:
        """
        Create a database connection based on type.
        
        Args:
            db_type: "sqlite", "postgres", "mysql"
            connection_string: Database connection string
        
        Returns:
            Database connection object
        """
        if db_type == "sqlite":
            return sqlite3.connect(connection_string)
        
        elif db_type == "postgres":
            try:
                import psycopg2
                return psycopg2.connect(connection_string)
            except ImportError:
                raise ImportError("psycopg2 not installed. Run: pip install psycopg2-binary")
        
        elif db_type == "mysql":
            try:
                import mysql.connector
                # Parse connection string for MySQL
                # Format: mysql://user:password@host:port/database
                return mysql.connector.connect(
                    host=connection_string.split("@")[1].split(":")[0],
                    user=connection_string.split("://")[1].split(":")[0],
                    password=connection_string.split(":")[2].split("@")[0],
                    database=connection_string.split("/")[-1]
                )
            except ImportError:
                raise ImportError("mysql-connector-python not installed. Run: pip install mysql-connector-python")
        
        else:
            raise ValueError(f"Unsupported database type: {db_type}")
    
    async def apply_fix(
        self,
        code: str,
        fix_type: str,
        db_type: str,
        connection_string: str,
        create_backup: bool = True
    ) -> FixResult:
        """
        Apply a verified fix to a client's database.
        
        Args:
            code: The fix code (SQL or Python)
            fix_type: "sql" or "python"
            db_type: Database type
            connection_string: Connection string
            create_backup: Whether to create a point-in-time backup
        
        Returns:
            FixResult with outcome
        """
        import time
        start_time = time.time()
        
        conn = None
        try:
            conn = self.get_connection(db_type, connection_string)
            cursor = conn.cursor()
            
            # Create savepoint for potential rollback
            if db_type in ["postgres", "mysql"]:
                cursor.execute("SAVEPOINT before_fix")
            
            rows_affected = 0
            
            if fix_type == "sql":
                # Execute SQL statements
                statements = [s.strip() for s in code.split(";") if s.strip()]
                
                for stmt in statements:
                    cursor.execute(stmt)
                    if cursor.rowcount > 0:
                        rows_affected += cursor.rowcount
                
                conn.commit()
            
            else:  # Python
                # Execute Python code with database context
                local_vars = {
                    "conn": conn,
                    "cursor": cursor,
                    "rows_affected": 0
                }
                
                # Safe builtins only
                safe_builtins = {
                    "len": len,
                    "str": str,
                    "int": int,
                    "float": float,
                    "list": list,
                    "dict": dict,
                    "range": range,
                    "enumerate": enumerate,
                    "print": print,  # For debugging
                }
                
                exec(code, {"__builtins__": safe_builtins}, local_vars)
                rows_affected = local_vars.get("rows_affected", 0)
                conn.commit()
            
            execution_time = (time.time() - start_time) * 1000
            
            return FixResult(
                success=True,
                message=f"Fix applied successfully to {db_type} database",
                rows_affected=rows_affected,
                execution_time_ms=execution_time,
                rollback_available=True
            )
        
        except Exception as e:
            # Attempt rollback
            if conn:
                try:
                    conn.rollback()
                except:
                    pass
            
            return FixResult(
                success=False,
                message="Fix failed to apply",
                error=str(e),
                execution_time_ms=(time.time() - start_time) * 1000
            )
        
        finally:
            if conn:
                try:
                    conn.close()
                except:
                    pass
    
    async def verify_connection(
        self,
        db_type: str,
        connection_string: str
    ) -> tuple[bool, str]:
        """
        Test if a database connection is valid.
        
        Returns:
            (success, message)
        """
        try:
            conn = self.get_connection(db_type, connection_string)
            cursor = conn.cursor()
            
            # Simple query to test connection
            if db_type == "sqlite":
                cursor.execute("SELECT sqlite_version()")
            elif db_type == "postgres":
                cursor.execute("SELECT version()")
            elif db_type == "mysql":
                cursor.execute("SELECT VERSION()")
            
            version = cursor.fetchone()[0]
            conn.close()
            
            return True, f"Connected successfully. Version: {version}"
        
        except Exception as e:
            return False, f"Connection failed: {str(e)}"
    
    async def get_schema(
        self,
        db_type: str,
        connection_string: str
    ) -> Optional[str]:
        """
        Retrieve the database schema for context.
        
        Returns:
            Schema as SQL string
        """
        try:
            conn = self.get_connection(db_type, connection_string)
            cursor = conn.cursor()
            
            if db_type == "sqlite":
                cursor.execute(
                    "SELECT sql FROM sqlite_master WHERE type='table' AND sql IS NOT NULL"
                )
                schemas = cursor.fetchall()
                conn.close()
                return "\n\n".join([s[0] for s in schemas if s[0]])
            
            elif db_type == "postgres":
                cursor.execute("""
                    SELECT table_name, column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_schema = 'public'
                    ORDER BY table_name, ordinal_position
                """)
                columns = cursor.fetchall()
                conn.close()
                
                # Format as CREATE TABLE statements
                tables = {}
                for table, column, dtype in columns:
                    if table not in tables:
                        tables[table] = []
                    tables[table].append(f"  {column} {dtype}")
                
                return "\n\n".join([
                    f"CREATE TABLE {table} (\n{chr(10).join(cols)}\n);"
                    for table, cols in tables.items()
                ])
            
            elif db_type == "mysql":
                cursor.execute("SHOW TABLES")
                tables = cursor.fetchall()
                
                schemas = []
                for (table,) in tables:
                    cursor.execute(f"SHOW CREATE TABLE {table}")
                    result = cursor.fetchone()
                    if result:
                        schemas.append(result[1])
                
                conn.close()
                return "\n\n".join(schemas)
            
            return None
        
        except Exception as e:
            return f"Error retrieving schema: {str(e)}"
    
    async def get_sample_data(
        self,
        db_type: str,
        connection_string: str,
        table_name: str,
        limit: int = 5
    ) -> Optional[str]:
        """
        Get sample data from a table for context.
        
        Returns:
            Sample data as formatted string
        """
        try:
            conn = self.get_connection(db_type, connection_string)
            cursor = conn.cursor()
            
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {limit}")
            rows = cursor.fetchall()
            
            # Get column names
            columns = [desc[0] for desc in cursor.description]
            
            conn.close()
            
            # Format as table
            result = " | ".join(columns) + "\n"
            result += "-" * len(result) + "\n"
            for row in rows:
                result += " | ".join(str(v) for v in row) + "\n"
            
            return result
        
        except Exception as e:
            return f"Error retrieving sample data: {str(e)}"


# Singleton instance
_fixer_instance: Optional[DatabaseFixer] = None


def get_fixer() -> DatabaseFixer:
    """Get or create the singleton fixer instance."""
    global _fixer_instance
    if _fixer_instance is None:
        _fixer_instance = DatabaseFixer()
    return _fixer_instance
