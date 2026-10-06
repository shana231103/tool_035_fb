# File: backend/app/infrastructure/automation/meta_otp_observer_geometry.py

# Read-only DOM inspection. Never reads an input value or modifies provider markup.
CODE_FIELD_EVIDENCE = r"""control => {
    const visible = node => {
        const box = node.getBoundingClientRect();
        if (box.width <= 0 || box.height <= 0) return false;
        for (let ancestor = node; ancestor; ancestor = ancestor.parentElement) {
            const style = getComputedStyle(ancestor);
            if (style.visibility !== 'visible' || style.display === 'none' || Number(style.opacity) <= 0) return false;
        }
        return true;
    };
    const green = node => ['stroke', 'fill', 'color'].some(property => {
        const style = getComputedStyle(node), raw = style[property];
        if (!raw) return false;
        if (Number(style[property+'Opacity']) <= 0 ||
                (property === 'stroke' && parseFloat(style.strokeWidth) <= 0)) return false;
        const parts = raw.match(/^rgba?\(\s*([\d.]+)[ ,]+([\d.]+)[ ,]+([\d.]+)(?:[ ,/]+([\d.]+))?\s*\)$/);
        if (!parts) return false;
        const [r, g, b] = parts.slice(1, 4).map(Number);
        return (parts[4] === undefined || Number(parts[4]) > 0) &&
            g >= 60 && g > r * 1.2 && g > b * 1.1;
    });
    const geometry = path => {
        try {
            const length = path.getTotalLength();
            if (length <= 0) return null;
            const start = path.getPointAtLength(0), end = path.getPointAtLength(length);
            let bottom = start, left = start.x, right = start.x, top = start.y;
            for (let i = 1; i <= 40; i++) {
                const point = path.getPointAtLength(length * i / 40);
                if (point.y > bottom.y) bottom = point;
                left = Math.min(left, point.x); right = Math.max(right, point.x);
                top = Math.min(top, point.y);
            }
            const box = {x:left, y:top, width:right-left, height:bottom.y-top};
            if (box.width <= 0 || box.height <= 0) return null;
            return {box, closed: Math.hypot(start.x-end.x, start.y-end.y) < length*.02,
                tick: start.x < bottom.x && bottom.x < end.x &&
                    bottom.y-start.y > box.height*.35 && bottom.y-end.y > box.height*.35};
        } catch { return null; }
    };
    let field = control.parentElement, indicator = false;
    for (let depth = 0; field && depth < 5; depth++, field = field.parentElement) {
        // Never climb into another field, a form action, or the overall page.
        if (field.matches('form, body') || field.querySelectorAll('input,textarea,select').length !== 1 ||
                field.querySelector('button,[role="button"]:not([aria-label="Clear text"])')) break;
        indicator = [...field.querySelectorAll('svg')].some(svg => {
            if (!visible(svg)) return false;
            const hasValidTitle = ['title', 'aria-label'].some(attr => {
                const val = (svg.getAttribute(attr) || '').toLowerCase();
                return val.includes('valid') && !val.includes('invalid');
            }) || (svg.querySelector('title')?.textContent || '').toLowerCase().includes('valid');

            const shapes = [...svg.querySelectorAll('path,polyline,circle,ellipse')]
                .filter(shape => visible(shape) && (green(shape) || green(svg)));
            if (shapes.length === 0 && !green(svg)) return false;

            if (hasValidTitle && (green(svg) || shapes.some(s => green(s)))) return true;

            const paths = shapes.flatMap(shape => {
                const data = shape.matches('path') ? shape.getAttribute('d') || '' : '';
                const parts = data.split(/(?=M)/).filter(part => part.trim());
                if (parts.length <= 1) return [{shape, geometry:geometry(shape)}];
                // Detached geometry only; do not append or change provider DOM.
                return parts.map(part => {
                    const fragment = document.createElementNS('http://www.w3.org/2000/svg','path');
                    fragment.setAttribute('d',part);
                    return {shape, geometry:geometry(fragment)};
                });
            });
            return paths.some(check => check.geometry?.tick && paths.some(ring => {
                if (ring === check || !ring.geometry) return false;
                const outer = ring.geometry.box, inner = check.geometry.box;
                const round = ring.shape.matches('circle,ellipse') ||
                    (ring.geometry.closed && outer.width/outer.height > .7 && outer.width/outer.height < 1.3);
                return round && outer.x <= inner.x && outer.y <= inner.y &&
                    outer.x+outer.width >= inner.x+inner.width && outer.y+outer.height >= inner.y+inner.height;
            }));
        });
        if (indicator) break;
    }
    return {connected: control.isConnected, locked: control.disabled || control.readOnly,
        positive: indicator};
}"""
