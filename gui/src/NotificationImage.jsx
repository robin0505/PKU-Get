import { useState, useEffect } from 'react';

// Helper to get the API
const getApi = () => {
    if (window.pywebview && window.pywebview.api && typeof window.pywebview.api.get_init_state === 'function') {
        return window.pywebview.api;
    }
    return null;
};

export function NotificationImage({ src, alt, courseName, ...props }) {
    const [imageSrc, setImageSrc] = useState(null);
    const [loading, setLoading] = useState(true);

    useEffect(() => {
        const loadImage = async () => {
            // Only process relative paths (assets/...)
            if (src && src.startsWith('assets/')) {
                try {
                    const api = getApi();
                    if (api && api.get_notification_image) {
                        const dataUri = await api.get_notification_image(courseName, src);
                        if (dataUri) {
                            setImageSrc(dataUri);
                        }
                    }
                } catch (err) {
                    console.error('Failed to load image:', src, err);
                } finally {
                    setLoading(false);
                }
            } else {
                // For absolute URLs, use them directly
                setImageSrc(src);
                setLoading(false);
            }
        };

        loadImage();
    }, [src, courseName]);

    if (loading) {
        return (
            <div className="flex items-center justify-center h-48 bg-slate-100 dark:bg-slate-700 rounded-lg my-4">
                <div className="text-slate-400 text-sm">Loading image...</div>
            </div>
        );
    }

    if (!imageSrc) {
        return (
            <div className="flex items-center justify-center h-48 bg-slate-100 dark:bg-slate-700 rounded-lg my-4">
                <div className="text-slate-400 text-sm">Image not available</div>
            </div>
        );
    }

    return (
        <img
            {...props}
            src={imageSrc}
            alt={alt || ''}
            className="max-w-full h-auto my-4 rounded-lg shadow-md"
            loading="lazy"
        />
    );
}
