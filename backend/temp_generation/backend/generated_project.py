from flask import Flask, render_template_string, jsonify

app = Flask(__name__)

# 2. Create a frontend HTML file with a button and display area.
# 3. Include CSS inline in HTML for basic styling.
# 4. Connect frontend to backend using fetch API.
HTML_CONTENT = """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Flask Frontend-Backend Demo</title>
    <style>
        body {
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            min-height: 100vh;
            margin: 0;
            background-color: #f4f4f4;
            color: #333;
        }
        .container {
            background-color: #fff;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 4px 10px rgba(0, 0, 0, 0.1);
            text-align: center;
            width: 90%;
            max-width: 500px;
        }
        h1 {
            color: #0056b3;
            margin-bottom: 25px;
        }
        button {
            padding: 12px 25px;
            font-size: 1.1em;
            background-color: #007bff;
            color: white;
            border: none;
            border-radius: 5px;
            cursor: pointer;
            transition: background-color 0.3s ease, transform 0.2s ease;
            margin-bottom: 20px;
        }
        button:hover {
            background-color: #0056b3;
            transform: translateY(-2px);
        }
        button:active {
            transform: translateY(0);
        }
        #displayArea {
            margin-top: 20px;
            padding: 15px;
            border: 1px solid #ddd;
            border-radius: 5px;
            background-color: #e9ecef;
            min-height: 50px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 1.2em;
            color: #28a745; /* Green for success message */
            word-wrap: break-word;
            text-align: center;
        }
        #displayArea.error {
            color: #dc3545; /* Red for error message */
        }
    </style>
</head>
<body>
    <div class="container">
        <h1>Frontend-Backend Interaction</h1>
        <button id="fetchButton">Say Hello to Backend</button>
        <div id="displayArea">Click the button to get a message from the backend!</div>
    </div>

    <script>
        document.getElementById('fetchButton').addEventListener('click', async () => {
            const displayArea = document.getElementById('displayArea');
            displayArea.textContent = 'Fetching data...';
            displayArea.classList.remove('error'); // Clear any previous error styling

            try {
                const response = await fetch('/hello');
                if (!response.ok) {
                    throw new Error(`HTTP error! status: ${response.status}`);
                }
                const data = await response.json();
                displayArea.textContent = data.message;
            } catch (error) {
                console.error('Error fetching data:', error);
                displayArea.textContent = `Error: Could not connect to backend or retrieve data. (${error.message})`;
                displayArea.classList.add('error'); // Add error styling
            }
        });
    </script>
</body>
</html>
"""

# Route to serve the HTML frontend
@app.route('/')
def index():
    return render_template_string(HTML_CONTENT)

# 1. Create a backend Flask app with a simple route '/hello'.
@app.route('/hello')
def hello():
    """
    A simple backend route that returns a JSON message.
    """
    return jsonify({"message": "Hello from Flask backend!"})

if __name__ == '__main__':
    # Run the Flask app
    # debug=True allows for automatic reloading on code changes and provides a debugger
    app.run(debug=True)