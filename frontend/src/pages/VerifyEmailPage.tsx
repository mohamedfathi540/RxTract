import { useEffect, useRef, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { authApi } from "../api/auth";

export function VerifyEmailPage() {
    const [searchParams] = useSearchParams();
    const token = searchParams.get("token");

    const [status, setStatus] = useState<"loading" | "success" | "error">(
        "loading"
    );
    const [message, setMessage] = useState("");
    const calledRef = useRef(false);

    useEffect(() => {
        if (!token) {
            setStatus("error");
            setMessage("No verification token provided.");
            return;
        }

        // Prevent React strict-mode double-invocation from consuming
        // the token twice (second call would get 400).
        if (calledRef.current) return;
        calledRef.current = true;

        authApi
            .verifyEmail(token)
            .then((res) => {
                setStatus("success");
                setMessage(res.message);
            })
            .catch((err) => {
                setStatus("error");
                const detail =
                    err?.response?.data?.detail ??
                    err?.message ??
                    "Verification failed. The token may be invalid or expired.";
                setMessage(detail);
            });
    }, [token]);

    return (
        <div className="min-h-screen flex items-center justify-center bg-bg-primary p-4">
            <div className="w-full max-w-md animate-slide-up">
                <div className="bg-bg-card border border-border rounded-xl p-8 text-center space-y-5 shadow-lg shadow-black/30">
                    {status === "loading" && (
                        <>
                            <div className="flex justify-center">
                                <svg
                                    className="animate-spin h-10 w-10 text-primary-500"
                                    viewBox="0 0 24 24"
                                    fill="none"
                                >
                                    <circle
                                        className="opacity-25"
                                        cx="12"
                                        cy="12"
                                        r="10"
                                        stroke="currentColor"
                                        strokeWidth="4"
                                    />
                                    <path
                                        className="opacity-75"
                                        fill="currentColor"
                                        d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4z"
                                    />
                                </svg>
                            </div>
                            <p className="text-text-secondary text-sm">
                                Verifying your email…
                            </p>
                        </>
                    )}

                    {status === "success" && (
                        <>
                            <div className="flex justify-center">
                                <div className="w-16 h-16 rounded-full bg-success/15 flex items-center justify-center">
                                    <svg
                                        className="w-8 h-8 text-success"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                        strokeWidth={2.5}
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            d="M5 13l4 4L19 7"
                                        />
                                    </svg>
                                </div>
                            </div>
                            <h2 className="text-xl font-semibold text-white">{message}</h2>
                            <Link
                                to="/login"
                                className="inline-block mt-2 px-6 py-2.5 bg-primary-600 hover:bg-primary-700 text-white text-sm font-medium rounded-lg transition-colors"
                            >
                                Go to Login
                            </Link>
                        </>
                    )}

                    {status === "error" && (
                        <>
                            <div className="flex justify-center">
                                <div className="w-16 h-16 rounded-full bg-error/15 flex items-center justify-center">
                                    <svg
                                        className="w-8 h-8 text-error"
                                        fill="none"
                                        viewBox="0 0 24 24"
                                        stroke="currentColor"
                                        strokeWidth={2.5}
                                    >
                                        <path
                                            strokeLinecap="round"
                                            strokeLinejoin="round"
                                            d="M6 18L18 6M6 6l12 12"
                                        />
                                    </svg>
                                </div>
                            </div>
                            <h2 className="text-xl font-semibold text-white">
                                Verification Failed
                            </h2>
                            <p className="text-text-secondary text-sm">{message}</p>
                            <Link
                                to="/login"
                                className="inline-block mt-2 px-6 py-2.5 bg-bg-tertiary hover:bg-bg-hover border border-border text-text-primary text-sm font-medium rounded-lg transition-colors"
                            >
                                Back to Login
                            </Link>
                        </>
                    )}
                </div>
            </div>
        </div>
    );
}
