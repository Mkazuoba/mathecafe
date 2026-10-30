/** Reduz a imagem escolhida (lado maior até `ladoMaximo` px) e devolve um
 * JPEG em data URL: é assim que fotos e cartazes vão ao servidor. */
export function reduzirImagem(arquivo: File, ladoMaximo: number, qualidade = 0.85): Promise<string> {
  return new Promise((resolve, reject) => {
    const url = URL.createObjectURL(arquivo)
    const img = new Image()
    img.onload = () => {
      const escala = Math.min(1, ladoMaximo / Math.max(img.width, img.height))
      const canvas = document.createElement("canvas")
      canvas.width = Math.round(img.width * escala)
      canvas.height = Math.round(img.height * escala)
      canvas.getContext("2d")!.drawImage(img, 0, 0, canvas.width, canvas.height)
      URL.revokeObjectURL(url)
      resolve(canvas.toDataURL("image/jpeg", qualidade))
    }
    img.onerror = () => {
      URL.revokeObjectURL(url)
      reject(new Error("Não foi possível abrir essa imagem"))
    }
    img.src = url
  })
}
