from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
import requests
from sqlalchemy import func
import plotly.graph_objects as go
import pandas as pd

app = Flask(__name__)

# Configuration for the SQLite database
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///transactions.db'
db = SQLAlchemy(app)

# Transaction Model
class Transaction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    product_title = db.Column(db.String(200), nullable=False)
    product_description = db.Column(db.String(500), nullable=True)
    price = db.Column(db.Float, nullable=False)
    date_of_sale = db.Column(db.String(100), nullable=False)
    sold = db.Column(db.Boolean, nullable=False)
    category = db.Column(db.String(100), nullable=True)

# Initialize the database and seed it with data from the third-party API
@app.route('/initialize', methods=['GET'])
def initialize_database():
    url = "https://s3.amazonaws.com/roxiler.com/product_transaction.json"
    response = requests.get(url)
    data = response.json()

    # Clear existing data
    Transaction.query.delete()

    # Insert new data
    for item in data:
        transaction = Transaction(
            product_title=item.get('title'),
            product_description=item.get('description'),
            price=item.get('price'),
            date_of_sale=item.get('dateOfSale'),
            sold=item.get('sold'),
            category=item.get('category')
        )
        db.session.add(transaction)

    db.session.commit()
    return jsonify({"message": "Database initialized with seed data."}), 201

# API to list all transactions with search and pagination
@app.route('/transactions', methods=['GET'])
def list_transactions():
    page = request.args.get('page', 1, type=int)
    per_page = request.args.get('per_page', 10, type=int)
    search = request.args.get('search', '', type=str)

    query = Transaction.query

    if search:
        query = query.filter(
            (Transaction.product_title.ilike(f'%{search}%')) |
            (Transaction.product_description.ilike(f'%{search}%')) |
            (Transaction.price.ilike(f'%{search}%'))
        )

    transactions = query.paginate(page=page, per_page=per_page, error_out=False)

    results = [{
        'product_title': t.product_title,
        'price': t.price,
        'sold': t.sold,
        'date_of_sale': t.date_of_sale,
        'category': t.category
    } for t in transactions.items]

    return jsonify({
        'transactions': results,
        'total': transactions.total,
        'pages': transactions.pages,
        'current_page': transactions.page
    })

# API for statistics
@app.route('/statistics', methods=['GET'])
def get_statistics():
    month = request.args.get('month', None)
    
    if not month:
        return jsonify({"error": "Please provide a month"}), 400

    month = month.capitalize()

    total_sales = db.session.query(func.sum(Transaction.price)).filter(
        func.strftime('%B', Transaction.date_of_sale) == month,
        Transaction.sold == True
    ).scalar()

    sold_items = db.session.query(func.count(Transaction.id)).filter(
        func.strftime('%B', Transaction.date_of_sale) == month,
        Transaction.sold == True
    ).scalar()

    unsold_items = db.session.query(func.count(Transaction.id)).filter(
        func.strftime('%B', Transaction.date_of_sale) == month,
        Transaction.sold == False
    ).scalar()

    return jsonify({
        'total_sales': total_sales or 0,
        'sold_items': sold_items or 0,
        'unsold_items': unsold_items or 0
    })

# API for bar chart (price range distribution)
@app.route('/price-range-bar-chart', methods=['GET'])
def price_range_bar_chart():
    month = request.args.get('month', None)

    if not month:
        return jsonify({"error": "Please provide a month"}), 400

    month = month.capitalize()

    price_ranges = [
        (0, 100), (101, 200), (201, 300), (301, 400), (401, 500),
        (501, 600), (601, 700), (701, 800), (801, 900), (901, float('inf'))
    ]
    price_range_labels = ['0-100', '101-200', '201-300', '301-400', '401-500', '501-600', '601-700', '701-800', '801-900', '901+']

    result = []
    
    for i, (low, high) in enumerate(price_ranges):
        count = db.session.query(func.count(Transaction.id)).filter(
            func.strftime('%B', Transaction.date_of_sale) == month,
            Transaction.price.between(low, high),
            Transaction.sold == True
        ).scalar()
        result.append({'Price Range': price_range_labels[i], 'Number of Items Sold': count})

    # Generate the bar chart
    df = pd.DataFrame(result)
    fig = go.Figure(data=[go.Bar(
        x=df['Price Range'],
        y=df['Number of Items Sold'],
        marker=dict(color='skyblue')
    )])

    fig.update_layout(
        title=f'Items Sold by Price Range for {month}',
        xaxis_title='Price Range',
        yaxis_title='Number of Items Sold',
    )

    fig.show()

    return jsonify(result)

# API for pie chart (category distribution)
@app.route('/category-pie-chart', methods=['GET'])
def category_pie_chart():
    month = request.args.get('month', None)

    if not month:
        return jsonify({"error": "Please provide a month"}), 400

    month = month.capitalize()

    categories = db.session.query(Transaction.category, func.count(Transaction.id)).filter(
        func.strftime('%B', Transaction.date_of_sale) == month
    ).group_by(Transaction.category).all()

    result = [{'category': c, 'count': count} for c, count in categories]

    labels = [r['category'] for r in result]
    values = [r['count'] for r in result]

    # Generate the pie chart
    fig = go.Figure(data=[go.Pie(labels=labels, values=values)])
    fig.update_layout(title=f'Category Distribution for {month}')
    fig.show()

    return jsonify(result)

# API to combine data from other APIs
@app.route('/combined-data', methods=['GET'])
def combined_data():
    month = request.args.get('month', None)

    if not month:
        return jsonify({"error": "Please provide a month"}), 400

    statistics = get_statistics().json
    bar_chart_data = price_range_bar_chart().json
    pie_chart_data = category_pie_chart().json

    return jsonify({
        'statistics': statistics,
        'price_range_data': bar_chart_data,
        'category_data': pie_chart_data
    })

if __name__ == '__main__':
    app.run(debug=True)

    
