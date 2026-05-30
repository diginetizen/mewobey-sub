from flask import Flask, render_template_string, request
import json
import os
import subprocess

app = Flask(__name__)

PORT = int(os.getenv("PORT", 2086))

HTML = """
<h2>XUI Dashboard</h2>

<form method="post" action="/sync">
<button>Sync Now</button>
</form>

<table border="1">
<tr><th>Email</th><th>SubID</th><th>File</th><th>Link</th></tr>

{% for k,v in data.items() %}
<tr>
<td>{{v.email}}</td>
<td>{{k}}</td>
<td>{{v.filename}}</td>
<td><a href="{{v.github_url}}">open</a></td>
</tr>
{% endfor %}
</table>
"""

def load():
    if not os.path.exists("submap.json"):
        return {}
    return json.load(open("submap.json"))

@app.route("/")
def index():
    return render_template_string(HTML, data=load())

@app.route("/sync", methods=["POST"])
def sync():
    subprocess.Popen(["python", "update.py", "sync"])
    return "<script>window.location='/'</script>"

app.run(host="127.0.0.1", port=PORT)
