function(source_repo, source_target_revision) {
    apiVersion: "argoproj.io/v1alpha1",
    kind: "Application",
    metadata: {
        name: "namespaces",
        namespace: "argocd",
        finalizers: ["resources-finalizer.argocd.argoproj.io"],
        annotations: {
            "argocd.argoproj.io/sync-wave": "1",
        },
    },
    spec: {
        project: "appproj-nippon-koku",
        source: {
            repoURL: source_repo,
            targetRevision: source_target_revision,
            path: "manifests/namespaces",
        },
        destination: {
            server: "https://kubernetes.default.svc",
        },
        syncPolicy: {
            automated: {
                selfHeal: true,
            },
        },
    },
}
