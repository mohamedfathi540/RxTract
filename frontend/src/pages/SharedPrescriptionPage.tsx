import { useState, useEffect } from "react";
import { useParams, Link } from "react-router-dom";
import { fetchSharedPrescription } from "../api/prescription";
import type { MedicineInfo } from "../api/types";
import { useSettingsStore } from "../stores/settingsStore";
import {
    Pill,
    FileText,
    StickyNote,
    Info,
    ExternalLink,
    ChevronUp,
    ChevronDown,
    Hospital,
    AlertTriangle
} from "lucide-react";

export function SharedPrescriptionPage() {
    const { token } = useParams<{ token: string }>();
    const [isLoading, setIsLoading] = useState(true);
    const [error, setError] = useState<string | null>(null);
    
    const [title, setTitle] = useState("Shared Prescription");
    const [previewUrl, setPreviewUrl] = useState<string | null>(null);
    const [ocrText, setOcrText] = useState<string>("");
    const [medicines, setMedicines] = useState<MedicineInfo[]>([]);
    const [signal, setSignal] = useState<string>("");
    const [doctorSpecialty, setDoctorSpecialty] = useState<string>("Unknown");
    const [showOcr, setShowOcr] = useState(false);
    const [isImageModalOpen, setIsImageModalOpen] = useState(false);

    useEffect(() => {
        if (token) {
            const loadData = async () => {
                setIsLoading(true);
                try {
                    const data = await fetchSharedPrescription(token);
                    const parsedPreviewUrl = data.image_url ? `${useSettingsStore.getState().apiUrl.replace(/\/api\/v1\/?$/, '')}${data.image_url}` : null;
                    
                    setOcrText(data.ocr_text);
                    setMedicines(data.medicines);
                    setSignal(data.signal);
                    setDoctorSpecialty(data.doctor_specialty || "Unknown");
                    setPreviewUrl(parsedPreviewUrl);
                    if (data.project_title) {
                        setTitle(data.project_title);
                    }
                } catch (error) {
                    console.error("Failed to load shared prescription", error);
                    setError("Failed to load this shared prescription. The link might be invalid or expired.");
                } finally {
                    setIsLoading(false);
                }
            };
            loadData();
        }
    }, [token]);

    if (isLoading) {
        return (
            <div className="flex flex-col items-center justify-center min-h-screen p-8 text-center bg-bg-primary">
                <div className="w-12 h-12 border-4 border-primary-500/20 border-t-primary-500 rounded-full animate-spin mb-4" />
                <h2 className="text-xl font-medium text-text-primary">Loading Prescription...</h2>
            </div>
        );
    }

    if (error) {
        return (
            <div className="flex flex-col items-center justify-center min-h-screen p-8 text-center bg-bg-primary">
                <div className="bg-red-500/10 border border-red-500/30 rounded-xl p-8 max-w-md w-full">
                    <AlertTriangle className="w-12 h-12 text-red-400 mx-auto mb-4" />
                    <h2 className="text-xl font-medium text-red-400 mb-2">Error</h2>
                    <p className="text-red-300/80 mb-6">{error}</p>
                    <Link to="/" className="inline-flex items-center gap-2 px-6 py-3 bg-primary-600 hover:bg-primary-500 text-white font-medium rounded-lg transition-colors">
                        Go to RxTract
                    </Link>
                </div>
            </div>
        );
    }

    return (
        <div className="min-h-screen bg-bg-primary p-4 sm:p-8">
            <div className="max-w-4xl mx-auto space-y-6">
                {/* Header */}
                <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4 border-b border-border pb-6">
                    <div>
                        <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
                            <Pill className="w-6 h-6 text-primary-400" /> {title}
                        </h1>
                        <p className="text-text-secondary mt-1">
                            Shared via RxTract Prescription Analyzer
                        </p>
                    </div>
                    <Link to="/" className="inline-flex items-center gap-2 px-4 py-2 bg-bg-secondary hover:bg-bg-hover text-text-primary font-medium border border-border rounded-lg transition-colors">
                        Create your own
                    </Link>
                </div>

                {/* Preview Image */}
                {previewUrl && (
                    <div className="border-2 border-border rounded-xl p-4 sm:p-8 text-center bg-bg-secondary">
                        <div className="space-y-4">
                            <img
                                src={previewUrl}
                                alt="Prescription preview"
                                className="max-h-64 mx-auto rounded-lg shadow-lg cursor-pointer hover:opacity-90 transition-opacity"
                                onClick={(e) => {
                                    e.stopPropagation();
                                    setIsImageModalOpen(true);
                                }}
                            />
                            <p className="text-sm text-text-secondary flex items-center justify-center gap-1">
                                <FileText className="w-4 h-4 inline shrink-0" /> Click to enlarge
                            </p>
                        </div>
                    </div>
                )}

                {/* Extracted Medicines */}
                {medicines.length > 0 && (
                    <div className="space-y-4">
                        <div className="flex items-center justify-between">
                            <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
                                <Pill className="w-5 h-5 text-primary-400" />
                                Extracted Medicines ({medicines.length})
                            </h2>
                            <div className="flex items-center gap-1.5 px-3 py-1 bg-bg-tertiary border border-border rounded-lg text-sm text-text-secondary">
                                <Hospital className="w-4 h-4 text-emerald-400" />
                                <span className="font-medium">Specialty:</span> {doctorSpecialty}
                            </div>
                        </div>

                        <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                            {medicines.map((cand, idx) => (
                                <div
                                    key={idx}
                                    className="bg-bg-secondary border border-border rounded-xl p-5 hover:border-primary-500/30 transition-colors shadow-sm"
                                >
                                    <div className="flex justify-between items-start mb-3 gap-2">
                                        <h3 className="font-semibold text-text-primary text-lg leading-tight">
                                            {cand.name}
                                        </h3>
                                        {cand.price && cand.price !== "Unknown" && (
                                            <span className="shrink-0 bg-primary-500/10 text-primary-400 px-2.5 py-1 rounded-md text-sm font-medium border border-primary-500/20">
                                                {cand.price}
                                            </span>
                                        )}
                                    </div>

                                    <div className="space-y-2 mb-4">
                                        {cand.active_ingredient && cand.active_ingredient !== "Unknown" && (
                                            <p className="text-sm flex items-start gap-2">
                                                <span className="text-text-muted w-20 shrink-0">Ingredient:</span>
                                                <span className="text-text-secondary font-medium">{cand.active_ingredient}</span>
                                            </p>
                                        )}
                                        {cand.dosage && cand.dosage !== "Unknown" && (
                                            <p className="text-sm flex items-start gap-2">
                                                <span className="text-text-muted w-20 shrink-0">Dosage:</span>
                                                <span className="text-text-secondary font-medium">{cand.dosage}</span>
                                            </p>
                                        )}
                                        {cand.form && cand.form !== "Unknown" && (
                                            <p className="text-sm flex items-start gap-2">
                                                <span className="text-text-muted w-20 shrink-0">Form:</span>
                                                <span className="text-text-secondary font-medium capitalize">{cand.form.replace(/_/g, " ")}</span>
                                            </p>
                                        )}
                                    </div>

                                    {/* Action buttons */}
                                    <div className="flex gap-2">
                                        {cand.product_url && cand.product_url !== "Unknown" && (
                                            <a
                                                href={cand.product_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-primary-600 hover:bg-primary-500 text-white text-xs font-medium rounded-lg transition-colors"
                                            >
                                                <ExternalLink className="w-3.5 h-3.5" /> View Product
                                            </a>
                                        )}
                                        {cand.image_url && cand.image_url !== "Unknown" && (
                                            <a
                                                href={cand.image_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="flex-1 flex items-center justify-center gap-1.5 px-3 py-2 bg-bg-tertiary hover:bg-bg-hover text-text-secondary text-xs font-medium rounded-lg border border-border transition-colors"
                                            >
                                                <ExternalLink className="w-3.5 h-3.5" /> View Images
                                            </a>
                                        )}
                                    </div>
                                </div>
                            ))}
                        </div>
                    </div>
                )}

                {/* Signal when no medicines found */}
                {signal && medicines.length === 0 && !error && (
                    <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4">
                        <p className="text-yellow-400 font-medium flex items-center gap-1.5"><Info className="w-4 h-4" /> {signal}</p>
                        <p className="text-yellow-300/80 text-sm mt-1">
                            The OCR was performed but no medicine names could be extracted.
                        </p>
                    </div>
                )}

                {/* OCR Text (collapsible) */}
                {ocrText && (
                    <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden mt-6">
                        <button
                            onClick={() => setShowOcr(!showOcr)}
                            className="w-full px-5 py-3 flex items-center justify-between hover:bg-bg-hover transition-colors"
                        >
                            <span className="text-sm font-medium text-text-secondary flex items-center gap-1.5">
                                <StickyNote className="w-4 h-4" /> Raw OCR Text
                            </span>
                            <span className="text-text-muted text-xs flex items-center gap-1">
                                {showOcr ? <><ChevronUp className="w-3 h-3" /> Hide</> : <><ChevronDown className="w-3 h-3" /> Show</>}
                            </span>
                        </button>
                        {showOcr && (
                            <div className="px-5 pb-5 pt-2 border-t border-border">
                                <pre className="text-xs text-text-muted whitespace-pre-wrap font-mono bg-bg-primary p-4 rounded-lg border border-border overflow-x-auto">
                                    {ocrText}
                                </pre>
                            </div>
                        )}
                    </div>
                )}

                {/* Full Image Modal */}
                {isImageModalOpen && previewUrl && (
                    <div 
                        className="fixed inset-0 z-[100] flex items-center justify-center p-4 bg-black/80 backdrop-blur-sm"
                        onClick={() => setIsImageModalOpen(false)}
                    >
                        <div className="relative max-w-7xl max-h-full w-full flex flex-col items-center justify-center" onClick={(e) => e.stopPropagation()}>
                            <button 
                                className="absolute top-4 right-4 p-2 bg-black/50 hover:bg-black/80 rounded-full text-white transition-colors z-10"
                                onClick={() => setIsImageModalOpen(false)}
                            >
                                <svg xmlns="http://www.w3.org/2000/svg" className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                                </svg>
                            </button>
                            <img 
                                src={previewUrl} 
                                alt="Full prescription" 
                                className="max-w-full max-h-[90vh] object-contain rounded-lg shadow-2xl"
                            />
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
