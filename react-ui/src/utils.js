
export function makeAPIURL(endpoint, query_params = null) {
    const url = new URL(`/api/${endpoint}`, window.location.origin);

    if (query_params) {
        Object.keys(query_params).forEach(key => url.searchParams.append(key, query_params[key]))
    }

    return url
}

export function sendAPIRequest(endpoint, query_params = null, method = 'GET', callback = null, post_object = null) {
    const url = makeAPIURL(endpoint, query_params)

    var requestOptions;
    if (post_object !== null) {
        const query = JSON.stringify(post_object);

        requestOptions = {
            method: method,
            headers: { 'Content-Type': 'application/json' },
            body: query
        };
    } else {
        requestOptions = {
            method: method,
            headers: { 'Content-Type': 'application/json' },
        };
    }

    return fetch(url, requestOptions)
        .then(response => {
            if (!response.ok) {
                console.log(`Error in api call to ${url}:`)
                console.dir(response)
                console.dir(response.json())
                return null
            }
            return response.json()
        })
        .then(data => {
            if (callback) {
                callback(data);
            } else {
                return data;
            }
        });
}
