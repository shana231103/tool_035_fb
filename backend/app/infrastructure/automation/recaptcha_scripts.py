# File: backend/app/infrastructure/automation/recaptcha_scripts.py
"""JavaScript evaluation scripts for reCAPTCHA Enterprise resolution and dismissal."""

DEFAULT_FB_ENTERPRISE_SITEKEY = "6LdktRgnAAAAAFQ6icovYI2-masYLFjEFyzQzpix"

FBSBX_INJECT_AND_NOTIFY_SCRIPT = r"""(token) => {
    let count = 0;
    let callbacksInvoked = 0;

    // 1. Inject token into all g-recaptcha-response textareas
    const textareas = document.querySelectorAll(
        'textarea[name="g-recaptcha-response"], textarea#g-recaptcha-response, [name="g-recaptcha-response"]'
    );
    textareas.forEach(el => {
        el.value = token;
        el.innerHTML = token;
        el.style.display = 'block';
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        count++;
    });

    // 2. Invoke Meta's container callback if present in window
    if (typeof window.successCallback === 'function') {
        try {
            window.successCallback(token);
            callbacksInvoked++;
        } catch (e) {
            console.warn('Error invoking window.successCallback:', e);
        }
    }

    // 3. Search and invoke reCAPTCHA callbacks in window.___grecaptcha_cfg
    if (window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {
        function findAndCallCallbacks(obj, depth = 0) {
            if (!obj || depth > 6) return;
            for (const key of Object.keys(obj)) {
                const val = obj[key];
                if (typeof val === 'function' && (key === 'callback' || key.toLowerCase().includes('callback'))) {
                    try {
                        val(token);
                        callbacksInvoked++;
                    } catch (err) {
                        console.warn('Error invoking recaptcha callback:', err);
                    }
                } else if (val && typeof val === 'object' && !Array.isArray(val)) {
                    findAndCallCallbacks(val, depth + 1);
                }
            }
        }
        for (const client of Object.values(window.___grecaptcha_cfg.clients)) {
            findAndCallCallbacks(client);
        }
    }

    // 4. Notify parent window via postMessage protocol
    if (window.parent && window.parent !== window) {
        try {
            window.parent.postMessage({ type: 'CAPTCHA_SOLVED', token: token }, '*');
            window.parent.postMessage(JSON.stringify({ type: 'CAPTCHA_SOLVED', token: token }), '*');
        } catch (e) {
            console.warn('Error posting CAPTCHA_SOLVED message to parent:', e);
        }
    }

    return { injected: count, callbacks: callbacksInvoked };
}"""

DISMISS_BFRAME_SCRIPT = r"""() => {
    let hiddenCount = 0;
    // Dismiss Google bframe popup and challenge containers
    const selectors = [
        'iframe[src*="recaptcha/enterprise/bframe"]',
        'iframe[src*="recaptcha/api2/bframe"]',
        'iframe[title*="challenge" i]',
        'div[style*="2147483647"]',
        '.g-recaptcha-bubble-arrow'
    ];
    selectors.forEach(sel => {
        document.querySelectorAll(sel).forEach(el => {
            el.style.display = 'none';
            el.style.visibility = 'hidden';
            el.style.pointerEvents = 'none';
            hiddenCount++;
        });
    });
    return hiddenCount;
}"""

EXTRACT_SITEKEY_SCRIPT = r"""() => {
    let sitekey = null;
    const el = document.querySelector('[data-sitekey]');
    if (el) {
        sitekey = el.getAttribute('data-sitekey');
    }
    if (!sitekey && window.___grecaptcha_cfg && window.___grecaptcha_cfg.clients) {
        function findSitekey(obj, depth = 0) {
            if (!obj || depth > 5) return null;
            for (const key of Object.keys(obj)) {
                const val = obj[key];
                if (key === 'sitekey' && typeof val === 'string' && val.length > 10) return val;
                if (val && typeof val === 'object' && !Array.isArray(val)) {
                    const found = findSitekey(val, depth + 1);
                    if (found) return found;
                }
            }
            return null;
        }
        for (const client of Object.values(window.___grecaptcha_cfg.clients)) {
            sitekey = findSitekey(client);
            if (sitekey) break;
        }
    }
    return { sitekey: sitekey, pageurl: window.location.href };
}"""
