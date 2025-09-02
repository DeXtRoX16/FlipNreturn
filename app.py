from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, session
from flask_mysqldb import MySQL
import MySQLdb.cursors
import bcrypt
from datetime import datetime, timedelta
import re

app = Flask(__name__)
app.secret_key = 'your-secret-key-here'

# MySQL Configuration
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_USER'] = 'root'
app.config['MYSQL_PASSWORD'] = 'sH@01062006'
app.config['MYSQL_DB'] = 'flipnreturn'

mysql = MySQL(app)

@app.route('/')
def index():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM books WHERE available = 1 LIMIT 6')
    featured_books = cursor.fetchall()
    cursor.close()
    return render_template('index.html', books=featured_books)

@app.route('/books')
def books():
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    search = request.args.get('search', '')
    category = request.args.get('category', '')
    
    query = 'SELECT * FROM books WHERE available = 1'
    params = []
    
    if search:
        query += ' AND (title LIKE %s OR author LIKE %s)'
        params.extend([f'%{search}%', f'%{search}%'])
    
    if category:
        query += ' AND category = %s'
        params.append(category)
    
    cursor.execute(query, params)
    all_books = cursor.fetchall()
    
    cursor.execute('SELECT DISTINCT category FROM books')
    categories = cursor.fetchall()
    
    cursor.close()
    return render_template('books.html', books=all_books, categories=categories)

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form['username']
        email = request.form['email']
        password = request.form['password']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s OR email = %s', (username, email))
        account = cursor.fetchone()
        
        if account:
            flash('Account already exists!')
        elif not re.match(r'[^@]+@[^@]+\.[^@]+', email):
            flash('Invalid email address!')
        elif not username or not password or not email:
            flash('Please fill out the form!')
        else:
            hashed_password = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt())
            cursor.execute('INSERT INTO users VALUES (NULL, %s, %s, %s, %s)', 
                        (username, email, hashed_password, datetime.now()))
            mysql.connection.commit()
            flash('You have successfully registered!')
            return redirect(url_for('login'))
        
        cursor.close()
    
    return render_template('register.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('SELECT * FROM users WHERE username = %s', (username,))
        account = cursor.fetchone()
        
        if account and bcrypt.checkpw(password.encode('utf-8'), account['password'].encode('utf-8')):
            session['loggedin'] = True
            session['id'] = account['id']
            session['username'] = account['username']
            return redirect(url_for('profile'))
        else:
            flash('Incorrect username/password!')
        
        cursor.close()
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('loggedin', None)
    session.pop('id', None)
    session.pop('username', None)
    return redirect(url_for('index'))

@app.route('/profile')
def profile():
    if 'loggedin' in session:
        cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
        cursor.execute('''SELECT b.title, b.author, br.issue_date, br.return_date, br.status 
                        FROM book_rentals br 
                        JOIN books b ON br.book_id = b.id 
                        WHERE br.user_id = %s 
                        ORDER BY br.issue_date DESC''', (session['id'],))
        rentals = cursor.fetchall()
        cursor.close()
        return render_template('profile.html', username=session['username'], rentals=rentals)
    
    return redirect(url_for('login'))

@app.route('/rent_book/<int:book_id>')
def rent_book(book_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Check if book is available
    cursor.execute('SELECT * FROM books WHERE id = %s AND available = 1', (book_id,))
    book = cursor.fetchone()
    
    if not book:
        flash('Book not available!')
        return redirect(url_for('books'))
    
    # Check if user already has this book
    cursor.execute('SELECT * FROM book_rentals WHERE user_id = %s AND book_id = %s AND status = "rented"', 
                (session['id'], book_id))
    existing = cursor.fetchone()
    
    if existing:
        flash('You already have this book!')
        return redirect(url_for('books'))
    
    # Create rental record
    issue_date = datetime.now()
    return_date = issue_date + timedelta(days=14)  # 2 weeks rental period
    
    cursor.execute('''INSERT INTO book_rentals (user_id, book_id, issue_date, return_date, status) 
                    VALUES (%s, %s, %s, %s, "rented")''', 
                (session['id'], book_id, issue_date, return_date))
    
    # Update book availability
    cursor.execute('UPDATE books SET available = 0 WHERE id = %s', (book_id,))
    
    mysql.connection.commit()
    cursor.close()
    
    flash('Book rented successfully!')
    return redirect(url_for('profile'))

@app.route('/return_book/<int:rental_id>')
def return_book(rental_id):
    if 'loggedin' not in session:
        return redirect(url_for('login'))
    
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    
    # Get rental info
    cursor.execute('SELECT * FROM book_rentals WHERE id = %s AND user_id = %s', 
                (rental_id, session['id']))
    rental = cursor.fetchone()
    
    if not rental:
        flash('Rental not found!')
        return redirect(url_for('profile'))
    
    # Update rental status
    cursor.execute('UPDATE book_rentals SET status = "returned", actual_return_date = %s WHERE id = %s', 
                (datetime.now(), rental_id))
    
    # Make book available again
    cursor.execute('UPDATE books SET available = 1 WHERE id = %s', (rental['book_id'],))
    
    mysql.connection.commit()
    cursor.close()
    
    flash('Book returned successfully!')
    return redirect(url_for('profile'))

@app.route('/api/search_books')
def api_search_books():
    query = request.args.get('q', '')
    cursor = mysql.connection.cursor(MySQLdb.cursors.DictCursor)
    cursor.execute('SELECT * FROM books WHERE (title LIKE %s OR author LIKE %s) AND available = 1 LIMIT 10', 
                (f'%{query}%', f'%{query}%'))
    books = cursor.fetchall()
    cursor.close()
    return jsonify(books)

if __name__ == '__main__':
    app.run(debug=True)