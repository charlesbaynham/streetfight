import gun_11 from './images/gun_11.svg';
import gun_16 from './images/gun_default.svg';
import gun_26 from './images/gun_26.svg';
import gun_36 from './images/gun_36.svg';


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

export function getGunImgFromUser(user) {
    let gun_name = null;

    if (user.shot_damage === 1 && user.shot_timeout === 6)
        gun_name = "damage1";
    else if (user.shot_damage === 2 && user.shot_timeout === 6)
        gun_name = "damage2";
    else if (user.shot_damage === 3 && user.shot_timeout === 6)
        gun_name = "damage3";
    else if (user.shot_damage === 1 && user.shot_timeout === 1)
        gun_name = "fast1";
    else
        return null


    const GUN_IMGS = {
        "damage1": gun_16,
        "damage2": gun_26,
        "damage3": gun_36,
        "fast1": gun_11,
    };

    return GUN_IMGS[gun_name];
}
