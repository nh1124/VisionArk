fetch('http://backend:8000/api/skills')
    .then(res => {
        console.log(`Status: ${res.status}`);
        return res.text();
    })
    .then(text => console.log(`Body (first 100 chars): ${text.substring(0, 100)}`))
    .catch(err => console.error('Error:', err));
