import { useState, useRef, useCallback } from "react";
import { analyzePrescriptionStream } from "../api/prescription";
import type { OcrProgressEvent } from "../api/prescription";
import type { MedicineInfo } from "../api/types";
import { Button } from "../components/ui/Button";
import { useSettingsStore } from "../stores/settingsStore";
import {
    Upload,
    Search,
    Pill,
    FlaskConical,
    BookOpen,
    CheckCircle2,
    FileText,
    ClipboardList,
    ShoppingCart,
    Hospital,
    MessageCircle,
    StickyNote,
    AlertTriangle,
    Info,
    Images,
    Sparkles,
    HelpCircle,
    ExternalLink,
} from "lucide-react";

/** Convert a File to a data URL so it survives page switches */
function fileToDataUrl(file: File): Promise<string> {
    return new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result as string);
        reader.onerror = reject;
        reader.readAsDataURL(file);
    });
}

/** Pipeline step definitions */
const PIPELINE_STEPS = [
    { key: "upload", label: "Upload", icon: Upload },
    { key: "preprocess", label: "Preprocessing", icon: Sparkles },
    { key: "ocr", label: "OCR Processing", icon: Search },
    { key: "extraction", label: "Medicine Extraction", icon: Pill },
    { key: "enrichment", label: "Ingredient Lookup", icon: FlaskConical },
    { key: "indexing", label: "Indexing", icon: BookOpen },
    { key: "complete", label: "Complete", icon: CheckCircle2 },
];

export function PrescriptionPage() {
    const { prescriptionResult, setPrescriptionResult } = useSettingsStore();

    const [file, setFile] = useState<File | null>(null);
    const [previewUrl, setPreviewUrl] = useState<string | null>(
        prescriptionResult?.previewDataUrl ?? null
    );
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [currentStep, setCurrentStep] = useState("");
    const [stepDetail, setStepDetail] = useState("");
    const [progressPercent, setProgressPercent] = useState(0);
    const [ocrText, setOcrText] = useState<string>(
        prescriptionResult?.ocrText ?? ""
    );
    const [medicines, setMedicines] = useState<MedicineInfo[]>(
        prescriptionResult?.medicines ?? []
    );
    const [error, setError] = useState<string | null>(null);
    const [showOcr, setShowOcr] = useState(false);
    const [signal, setSignal] = useState<string>(
        prescriptionResult?.signal ?? ""
    );
    const fileInputRef = useRef<HTMLInputElement>(null);
    const [isDragging, setIsDragging] = useState(false);
    const abortRef = useRef<{ abort: () => void } | null>(null);

    const handleFile = useCallback(async (f: File) => {
        setFile(f);
        setError(null);
        const dataUrl = await fileToDataUrl(f);
        setPreviewUrl(dataUrl);
    }, []);

    const handleDrop = useCallback(
        (e: React.DragEvent) => {
            e.preventDefault();
            setIsDragging(false);
            const droppedFile = e.dataTransfer.files[0];
            if (droppedFile) handleFile(droppedFile);
        },
        [handleFile]
    );

    const handleAnalyze = () => {
        if (!file) return;
        setIsAnalyzing(true);
        setProgressPercent(0);
        setCurrentStep("upload");
        setStepDetail("Preparing upload...");
        setError(null);
        setMedicines([]);
        setOcrText("");
        setSignal("");

        const handle = analyzePrescriptionStream(
            file,
            // onProgress
            (event: OcrProgressEvent) => {
                setCurrentStep(event.step);
                setStepDetail(event.detail);
                setProgressPercent(event.progress);
            },
            // onResult
            (result) => {
                const newOcrText = result.ocr_text || "";
                const newMedicines = result.medicines || [];
                const newSignal = result.signal || "";
                const newProjectId = result.project_id ?? null;

                setOcrText(newOcrText);
                setMedicines(newMedicines);
                setSignal(newSignal);
                setIsAnalyzing(false);

                setPrescriptionResult({
                    ocrText: newOcrText,
                    medicines: newMedicines,
                    signal: newSignal,
                    previewDataUrl: previewUrl,
                    projectId: newProjectId,
                });
            },
            // onError
            (errorMsg) => {
                setError(errorMsg);
                setIsAnalyzing(false);
            }
        );

        abortRef.current = handle;
    };

    const handleReset = () => {
        if (abortRef.current) {
            abortRef.current.abort();
            abortRef.current = null;
        }
        setFile(null);
        setPreviewUrl(null);
        setMedicines([]);
        setOcrText("");
        setError(null);
        setSignal("");
        setShowOcr(false);
        setIsAnalyzing(false);
        setCurrentStep("");
        setStepDetail("");
        setProgressPercent(0);
        setPrescriptionResult(null);
    };

    /** Get the visual state of a pipeline step */
    const getStepState = (stepKey: string) => {
        if (!currentStep) return "pending";
        const currentIdx = PIPELINE_STEPS.findIndex(s => s.key === currentStep);
        const stepIdx = PIPELINE_STEPS.findIndex(s => s.key === stepKey);
        if (stepIdx < currentIdx) return "done";
        if (stepIdx === currentIdx) return "active";
        return "pending";
    };

    return (
        <div className="space-y-6">
            {/* Header */}
            <div>
                <h1 className="text-2xl font-bold text-text-primary flex items-center gap-2">
                    <Pill className="w-6 h-6 text-primary-400" /> Prescription Analyzer
                </h1>
                <p className="text-text-secondary mt-1">
                    Upload a prescription image to extract medicine names, active
                    ingredients, and pictures.
                </p>
            </div>

            {/* Upload Zone */}
            <div
                className={`relative border-2 border-dashed rounded-xl p-4 sm:p-8 text-center transition-all duration-200 cursor-pointer ${isDragging
                    ? "border-primary-500 bg-primary-500/10"
                    : previewUrl
                        ? "border-border bg-bg-secondary"
                        : "border-border hover:border-primary-600 hover:bg-bg-secondary/50"
                    }`}
                onDragOver={(e) => {
                    e.preventDefault();
                    setIsDragging(true);
                }}
                onDragLeave={() => setIsDragging(false)}
                onDrop={handleDrop}
                onClick={() => !previewUrl && fileInputRef.current?.click()}
            >
                <input
                    ref={fileInputRef}
                    type="file"
                    accept="image/jpeg,image/png,image/webp,application/pdf"
                    className="hidden"
                    onChange={(e) => {
                        const f = e.target.files?.[0];
                        if (f) handleFile(f);
                    }}
                />

                {previewUrl ? (
                    <div className="space-y-4">
                        <img
                            src={previewUrl}
                            alt="Prescription preview"
                            className="max-h-64 mx-auto rounded-lg shadow-lg"
                        />
                        <div className="flex items-center justify-center gap-3">
                            <p className="text-sm text-text-secondary flex items-center gap-1">
                                <FileText className="w-4 h-4 inline shrink-0" /> {file?.name ?? "Previous prescription"}{" "}
                                {file && (
                                    <span className="text-text-muted">
                                        ({((file.size || 0) / 1024).toFixed(1)} KB)
                                    </span>
                                )}
                            </p>
                            <button
                                onClick={(e) => {
                                    e.stopPropagation();
                                    handleReset();
                                }}
                                className="text-xs text-red-400 hover:text-red-300 underline"
                            >
                                Remove
                            </button>
                        </div>
                    </div>
                ) : (
                    <div className="space-y-3">
                        <ClipboardList className="w-12 h-12 text-text-muted" />
                        <p className="text-text-secondary font-medium">
                            Drop your prescription image here
                        </p>
                        <p className="text-sm text-text-muted">
                            or click to browse · JPG, PNG, WebP, PDF
                        </p>
                    </div>
                )}
            </div>

            {/* Analyze Button */}
            {(file || (previewUrl && !medicines.length)) && (
                <div className="flex gap-3">
                    <Button
                        onPress={handleAnalyze}
                        isLoading={isAnalyzing}
                        variant="primary"
                        isDisabled={!file || isAnalyzing}
                    >
                        {isAnalyzing
                            ? "Analyzing..."
                            : <><Search className="w-4 h-4 inline mr-1" /> Analyze Prescription</>}
                    </Button>
                    {!isAnalyzing && (
                        <Button onPress={handleReset} variant="ghost">
                            Clear
                        </Button>
                    )}
                </div>
            )}

            {/* ── Real-Time Progress Stepper ── */}
            {isAnalyzing && (
                <div className="bg-bg-secondary rounded-xl p-6 border border-border">
                    <div className="flex items-center gap-3 mb-5">
                        <div className="animate-spin w-5 h-5 border-2 border-primary-500 border-t-transparent rounded-full" />
                        <div>
                            <p className="text-text-primary font-medium">
                                Processing prescription...
                            </p>
                            <p className="text-sm text-text-muted mt-0.5">
                                {stepDetail}
                            </p>
                        </div>
                    </div>

                    {/* Step indicators */}
                    <div className="space-y-2.5">
                        {PIPELINE_STEPS.map((step) => {
                            const state = getStepState(step.key);
                            return (
                                <div
                                    key={step.key}
                                    className={`flex items-center gap-3 px-3 py-2 rounded-lg transition-all duration-300 ${state === "active"
                                            ? "bg-primary-600/15 border border-primary-600/30"
                                            : state === "done"
                                                ? "bg-green-500/10"
                                                : "opacity-40"
                                        }`}
                                >
                                    {/* Status icon */}
                                    <div className="w-6 h-6 flex items-center justify-center shrink-0">
                                        {state === "done" ? (
                                            <CheckCircle2 className="w-4 h-4 text-green-400" />
                                        ) : state === "active" ? (
                                            <div className="w-4 h-4 border-2 border-primary-400 border-t-transparent rounded-full animate-spin" />
                                        ) : (
                                            <step.icon className="w-4 h-4 text-text-muted" />
                                        )}
                                    </div>
                                    {/* Label */}
                                    <span
                                        className={`text-sm font-medium ${state === "active"
                                                ? "text-primary-400"
                                                : state === "done"
                                                    ? "text-green-400"
                                                    : "text-text-muted"
                                            }`}
                                    >
                                        {step.label}
                                    </span>
                                    {/* Active detail */}
                                    {state === "active" && stepDetail && (
                                        <span className="text-xs text-text-muted ml-auto hidden sm:inline">
                                            {stepDetail}
                                        </span>
                                    )}
                                </div>
                            );
                        })}
                    </div>

                    {/* Overall progress bar */}
                    <div className="mt-4 w-full bg-bg-tertiary rounded-full h-2 overflow-hidden">
                        <div
                            className="bg-gradient-to-r from-primary-600 to-primary-400 h-2 rounded-full transition-all duration-500 ease-out"
                            style={{ width: `${progressPercent}%` }}
                        />
                    </div>
                    <p className="text-xs text-text-muted text-right mt-1">
                        {progressPercent}%
                    </p>
                </div>
            )}

            {/* Error / Warning */}
            {error && (
                <div className={`rounded-xl p-4 ${
                    error.startsWith('__RATE_LIMIT__')
                        ? 'bg-yellow-500/10 border border-yellow-500/30'
                        : 'bg-red-500/10 border border-red-500/30'
                }`}>
                    <p className={`font-medium ${
                        error.startsWith('__RATE_LIMIT__') ? 'text-yellow-400' : 'text-red-400'
                    }`}>
                        <AlertTriangle className="w-4 h-4 inline mr-1" />
                        {error.startsWith('__RATE_LIMIT__') ? 'Quota Limit' : 'Error'}
                    </p>
                    <p className={`text-sm mt-1 ${
                        error.startsWith('__RATE_LIMIT__') ? 'text-yellow-300' : 'text-red-300'
                    }`}>
                        {error.startsWith('__RATE_LIMIT__') ? error.slice(14) : error}
                    </p>
                </div>
            )}

            {/* Results */}
            {medicines.length > 0 && (
                <div className="space-y-4">
                    <div className="flex items-center justify-between">
                        <h2 className="text-lg font-semibold text-text-primary flex items-center gap-2">
                            <Hospital className="w-5 h-5 text-primary-400" /> Medicines Found ({medicines.length})
                        </h2>
                        <div className="flex items-center gap-2">
                            <span className="text-xs px-2 py-1 rounded-full bg-green-500/20 text-green-400">
                                {signal}
                            </span>
                            <Button
                                variant="ghost"
                                size="sm"
                                onPress={handleReset}
                            >
                                New Analysis
                            </Button>
                        </div>
                    </div>

                    <div className="grid gap-4">
                        {medicines.map((med, idx) => (
                            <div
                                key={idx}
                                className="bg-bg-secondary border border-border rounded-xl p-5 hover:border-primary-600/50 transition-colors"
                            >
                                {/* Medicine Info */}
                                <div className="flex flex-col sm:flex-row items-start justify-between gap-4">
                                    <div className="flex-1 min-w-0">
                                        <h3 className="text-lg font-bold text-text-primary">
                                            <span className="text-primary-400 mr-1.5">
                                                {idx + 1}.
                                            </span>
                                            {med.name}
                                        </h3>
                                        <div className="mt-2 grid grid-cols-1 sm:grid-cols-3 gap-3">
                                            <div>
                                                <p className="text-xs font-medium text-text-muted uppercase tracking-wider">
                                                    Active Ingredient
                                                </p>
                                                <p className="text-text-secondary mt-0.5">
                                                    {med.active_ingredient || "Not found"}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-xs font-medium text-text-muted uppercase tracking-wider">
                                                    Dosage
                                                </p>
                                                <p className="text-text-secondary mt-0.5">
                                                    {med.dosage && med.dosage !== "Unknown" ? med.dosage : "Not found"}
                                                </p>
                                            </div>
                                            <div>
                                                <p className="text-xs font-medium text-text-muted uppercase tracking-wider">
                                                    Form
                                                </p>
                                                <p className="text-text-secondary mt-0.5 capitalize">
                                                    {med.form && med.form !== "Unknown" ? med.form : "Not found"}
                                                </p>
                                            </div>
                                        </div>
                                    </div>

                                    {/* Google Image Search Link */}
                                    <div className="shrink-0 self-start flex flex-col gap-2">
                                        {med.product_url && (
                                            <a
                                                href={med.product_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="flex items-center gap-2 px-4 py-2.5 bg-green-600/20 hover:bg-green-600/30 text-green-400 rounded-lg border border-green-600/30 transition-all duration-200 hover:scale-105 text-sm font-medium"
                                                onClick={(e) => e.stopPropagation()}
                                            >
                                                <ShoppingCart className="w-4 h-4" /> View Product
                                            </a>
                                        )}
                                        {med.image_url && (
                                            <a
                                                href={med.image_url}
                                                target="_blank"
                                                rel="noopener noreferrer"
                                                className="flex items-center gap-2 px-4 py-2.5 bg-primary-600/20 hover:bg-primary-600/30 text-primary-400 rounded-lg border border-primary-600/30 transition-all duration-200 hover:scale-105 text-sm font-medium"
                                                onClick={(e) => e.stopPropagation()}
                                            >
                                                <Images className="w-4 h-4" /> View Images
                                            </a>
                                        )}
                                    </div>
                                </div>

                                {/* ── "Did you mean?" candidate suggestions ── */}
                                {med.candidates && med.candidates.length > 0 && (
                                    <div className="mt-4 p-4 rounded-lg bg-amber-500/8 border border-amber-500/20">
                                        <p className="text-sm font-medium text-amber-400 flex items-center gap-1.5 mb-3">
                                            <HelpCircle className="w-4 h-4" />
                                            Did you mean one of these?
                                        </p>
                                        <div className="flex gap-2 flex-wrap">
                                            {med.candidates.map((cand) => (
                                                <a
                                                    key={cand.name}
                                                    href={cand.product_url || cand.image_url}
                                                    target="_blank"
                                                    rel="noopener noreferrer"
                                                    className="inline-flex items-center gap-1.5 px-3 py-1.5 text-xs font-medium bg-bg-tertiary hover:bg-amber-500/15 text-text-secondary hover:text-amber-300 border border-border hover:border-amber-500/40 rounded-full transition-all duration-200"
                                                >
                                                    {cand.name}
                                                    <ExternalLink className="w-3 h-3 opacity-50" />
                                                </a>
                                            ))}
                                        </div>
                                    </div>
                                )}
                            </div>
                        ))}
                    </div>

                    {/* Tip to use Chat */}
                    {prescriptionResult?.projectId && (
                        <div className="bg-primary-600/10 border border-primary-600/30 rounded-xl p-4">
                            <p className="text-primary-400 font-medium flex items-center gap-1.5"><MessageCircle className="w-4 h-4" /> Chat Available</p>
                            <p className="text-primary-300/80 text-sm mt-1">
                                Go to the <strong>Chat</strong> page to ask questions about these
                                medicines — find replacements, check interactions, and more.
                            </p>
                        </div>
                    )}
                </div>
            )}

            {/* Signal when no medicines found */}
            {signal && medicines.length === 0 && !isAnalyzing && !error && (
                <div className="bg-yellow-500/10 border border-yellow-500/30 rounded-xl p-4">
                    <p className="text-yellow-400 font-medium flex items-center gap-1.5"><Info className="w-4 h-4" /> {signal}</p>
                    <p className="text-yellow-300/80 text-sm mt-1">
                        The OCR was performed but no medicine names could be extracted. Try
                        a clearer image.
                    </p>
                </div>
            )}

            {/* OCR Text (collapsible) */}
            {ocrText && (
                <div className="bg-bg-secondary border border-border rounded-xl overflow-hidden">
                    <button
                        onClick={() => setShowOcr(!showOcr)}
                        className="w-full px-5 py-3 flex items-center justify-between hover:bg-bg-hover transition-colors"
                    >
                        <span className="text-sm font-medium text-text-secondary flex items-center gap-1.5">
                            <StickyNote className="w-4 h-4" /> Raw OCR Text
                        </span>
                        <span className="text-text-muted text-xs">
                            {showOcr ? "▲ Hide" : "▼ Show"}
                        </span>
                    </button>
                    {showOcr && (
                        <div className="px-5 pb-4 border-t border-border pt-3">
                            <pre className="text-sm text-text-muted whitespace-pre-wrap font-mono leading-relaxed">
                                {ocrText}
                            </pre>
                        </div>
                    )}
                </div>
            )}
        </div>
    );
}
