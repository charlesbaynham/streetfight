
export function sendAPIRequest(endpoint, query_params = null, method = 'GET', callback = null) {
    const url = new URL(`/api/${endpoint}`, document.baseURI);

    if (query_params) {
        Object.keys(query_params).forEach(key => url.searchParams.append(key, query_params[key]))
    }

    const requestOptions = {
        method: method,
        headers: { 'Content-Type': 'application/json' },
    };

    fetch(url, requestOptions)
        .then(response => response.json())
        .then(data => {
            if (callback) {
                callback(data);
            }
        });
}

export default null;
