// hookmap: build a small DDNet map from an ASCII layout (dev tool for task107, NOT shipped).
//
//   hookmap <layout.txt> <out.map>
//
// layout chars:  '.' air   '#' hookable ground (grass_main)   'x' unhookable (generic_unhookable)
//                'S' / 'D' spawn points (row-major order decides which one the first player gets)
// A background group (parallax 0) holds a vertical sky gradient; the game group holds the two
// design layers and the game layer.
#include <base/logger.h>
#include <base/system.h>

#include <engine/shared/datafile.h>
#include <engine/storage.h>

#include <game/mapitems.h>

#include <fstream>
#include <string>
#include <vector>

static void StrToInts(int *pInts, size_t NumInts, const char *pStr)
{
	for(size_t i = 0; i < NumInts; i++)
		pInts[i] = 0;
	unsigned char aBuf[64] = {0};
	str_copy((char *)aBuf, pStr, sizeof(aBuf));
	for(size_t i = 0; i < NumInts; i++)
	{
		pInts[i] = ((aBuf[i * 4 + 0] + 128) << 24) | ((aBuf[i * 4 + 1] + 128) << 16) | ((aBuf[i * 4 + 2] + 128) << 8) | (aBuf[i * 4 + 3] + 128);
	}
	pInts[NumInts - 1] &= 0xFFFFFF00;
}

static const int TILEMAP_ITEM_SIZE = sizeof(CMapItemLayerTilemap);

int main(int argc, const char **argv)
{
	CCmdlineFix CmdlineFix(&argc, &argv);
	log_set_global_logger_default();
	if(argc != 3)
	{
		dbg_msg("hookmap", "usage: hookmap <layout.txt> <out.map>");
		return 1;
	}
	std::ifstream In(argv[1]);
	std::vector<std::string> vRows;
	std::string Line;
	while(std::getline(In, Line))
	{
		if(!Line.empty() && Line.back() == '\r')
			Line.pop_back();
		if(Line.empty() || Line[0] == ';')
			continue;
		vRows.push_back(Line);
	}
	const int H = (int)vRows.size();
	int W = 0;
	for(auto &R : vRows)
		W = std::max(W, (int)R.size());
	auto At = [&](int x, int y) -> char {
		if(y < 0 || y >= H || x < 0 || x >= (int)vRows[y].size())
			return '.';
		return vRows[y][x];
	};

	std::vector<CTile> vGame(W * H), vGrass(W * H), vUnhook(W * H);
	for(auto *pV : {&vGame, &vGrass, &vUnhook})
		for(auto &T : *pV)
			T = CTile{0, 0, 0, 0};
	for(int y = 0; y < H; y++)
		for(int x = 0; x < W; x++)
		{
			const char C = At(x, y);
			CTile &G = vGame[y * W + x];
			if(C == '#')
			{
				G.m_Index = TILE_SOLID;
				const bool Up = At(x, y - 1) != '#', Dn = At(x, y + 1) != '#', Lf = At(x - 1, y) != '#', Rt = At(x + 1, y) != '#';
				int Idx = 1;
				if(Up && Lf)
					Idx = 4;
				else if(Up && Rt)
					Idx = 5;
				else if(Dn && Lf)
					Idx = 36;
				else if(Dn && Rt)
					Idx = 37;
				else if(Up)
					Idx = 16;
				else if(Dn)
					Idx = 52;
				else if(Lf)
					Idx = 20;
				else if(Rt)
					Idx = 21;
				vGrass[y * W + x].m_Index = Idx;
			}
			else if(C == 'x')
			{
				G.m_Index = TILE_NOHOOK;
				vUnhook[y * W + x].m_Index = 1;
			}
			else if(C == 'S' || C == 'D')
				G.m_Index = ENTITY_OFFSET + ENTITY_SPAWN;
		}

	std::unique_ptr<IStorage> pStorage = CreateLocalStorage();
	CDataFileWriter Writer;
	if(!Writer.Open(pStorage.get(), argv[2], IStorage::TYPE_ABSOLUTE))
	{
		dbg_msg("hookmap", "cannot open %s", argv[2]);
		return 1;
	}

	CMapItemVersion Version;
	Version.m_Version = 1;
	Writer.AddItem(MAPITEMTYPE_VERSION, 0, sizeof(Version), &Version);

	// external images
	const char *apImages[] = {"grass_main", "generic_unhookable"};
	for(int i = 0; i < 2; i++)
	{
		CMapItemImage_v2 Img;
		Img.m_Version = 2;
		Img.m_Width = 1024;
		Img.m_Height = 1024;
		Img.m_External = 1;
		Img.m_ImageName = Writer.AddData(str_length(apImages[i]) + 1, apImages[i]);
		Img.m_ImageData = -1;
		Img.m_MustBe1 = 1;
		Writer.AddItem(MAPITEMTYPE_IMAGE, i, sizeof(Img), &Img);
	}

	int LayerId = 0;
	// group 0: sky
	{
		CMapItemGroup Group = {};
		Group.m_Version = 3;
		Group.m_ParallaxX = 0;
		Group.m_ParallaxY = 0;
		Group.m_StartLayer = LayerId;
		Group.m_NumLayers = 1;
		StrToInts(Group.m_aName, 3, "Sky");
		Writer.AddItem(MAPITEMTYPE_GROUP, 0, sizeof(Group), &Group);

		CQuad Q = {};
		const int S = 1200 << 10;
		Q.m_aPoints[0] = {-S, -S};
		Q.m_aPoints[1] = {S, -S};
		Q.m_aPoints[2] = {-S, S};
		Q.m_aPoints[3] = {S, S};
		Q.m_aPoints[4] = {0, 0};
		const CColor Top = {94, 132, 174, 255}, Bottom = {204, 232, 255, 255};
		Q.m_aColors[0] = Top;
		Q.m_aColors[1] = Top;
		Q.m_aColors[2] = Bottom;
		Q.m_aColors[3] = Bottom;
		Q.m_PosEnv = -1;
		Q.m_ColorEnv = -1;
		CMapItemLayerQuads L = {};
		L.m_Layer.m_Version = 0;
		L.m_Layer.m_Type = LAYERTYPE_QUADS;
		L.m_Layer.m_Flags = 0;
		L.m_Version = 2;
		L.m_NumQuads = 1;
		L.m_Data = Writer.AddDataSwapped(sizeof(Q), &Q);
		L.m_Image = -1;
		StrToInts(L.m_aName, 3, "Sky");
		Writer.AddItem(MAPITEMTYPE_LAYER, LayerId++, sizeof(L), &L);
	}
	// group 1: game
	{
		CMapItemGroup Group = {};
		Group.m_Version = 3;
		Group.m_ParallaxX = 100;
		Group.m_ParallaxY = 100;
		Group.m_StartLayer = LayerId;
		Group.m_NumLayers = 3;
		StrToInts(Group.m_aName, 3, "Game");
		Writer.AddItem(MAPITEMTYPE_GROUP, 1, sizeof(Group), &Group);

		auto AddTiles = [&](std::vector<CTile> &vTiles, int Image, int Flags, const char *pName) {
			CMapItemLayerTilemap L = {};
			L.m_Layer.m_Version = 0;
			L.m_Layer.m_Type = LAYERTYPE_TILES;
			L.m_Layer.m_Flags = 0;
			L.m_Version = 3;
			L.m_Width = W;
			L.m_Height = H;
			L.m_Flags = Flags;
			L.m_Color = {255, 255, 255, 255};
			L.m_ColorEnv = -1;
			L.m_ColorEnvOffset = 0;
			L.m_Image = Image;
			L.m_Data = Writer.AddData(vTiles.size() * sizeof(CTile), vTiles.data());
			StrToInts(L.m_aName, 3, pName);
			L.m_Tele = -1;
			L.m_Speedup = -1;
			L.m_Front = -1;
			L.m_Switch = -1;
			L.m_Tune = -1;
			Writer.AddItem(MAPITEMTYPE_LAYER, LayerId++, TILEMAP_ITEM_SIZE, &L);
		};
		AddTiles(vUnhook, 1, 0, "Unhook");
		AddTiles(vGrass, 0, 0, "Grass");
		AddTiles(vGame, -1, TILESLAYERFLAG_GAME, "Game");
	}

	Writer.Finish();
	dbg_msg("hookmap", "wrote %s (%dx%d)", argv[2], W, H);
	return 0;
}
